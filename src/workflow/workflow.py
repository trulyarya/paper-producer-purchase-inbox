import sys
from pathlib import Path

# Ensure the repository's src/ directory is importable when running as a script.
# resolve() gets absolute path; parents[1] goes up two levels
PROJECT_SRC = Path(__file__).resolve().parents[1]  # this gets us to the src/ directory
sys.path.insert(0, str(PROJECT_SRC))  # add src to sys.path, index '0' means beginning of the list

from agent_framework import (
    WorkflowBuilder,  # Builder class for constructing workflows (includes .add(), etc. methods)
    WorkflowContext,  # Controlled interface for executors to interact w broader workflow ecosystem
    AgentExecutorResponse,  # Response object returned by agent executors
    executor,  # Decorator converts standalone functions to FunctionExecutor instances
)

from agents import (
    classifier,
    parser,
    retriever,
    fact_checker,
    decider,
    fulfiller,
    rejector,
)

from agents.tool_capture import clear_evidence

from emailing.gmail_tools import (
    fetch_unread_emails,  # this is NOT the AI function get_unread_emails!
    mark_email_as_read
)

from loguru import logger


def should_parse(resp) -> bool:
    """Route to parser only if email is a PO."""
    return resp.agent_run_response.value.is_po


def should_fulfill(resp) -> bool:
    """Route to fulfiller if order is fulfillable."""
    return resp.agent_run_response.value.status == "FULFILLABLE"


def should_reject(resp) -> bool:
    """Route to rejector if order is unfulfillable."""
    return resp.agent_run_response.value.status == "UNFULFILLABLE"


def should_be_grounded(resp) -> bool:
    """Route to decider if retriever agent response passes the groundedness verification."""
    return resp.agent_run_response.value.is_grounded


@executor  # Decorator to make this function an executor in the workflow graph
def log_fulfillment(fulfillment_response: AgentExecutorResponse, ctx: WorkflowContext) -> None:
    """Terminal logger for successful fulfillment runs."""
    fulfillment_result = fulfillment_response.agent_run_response.value
    logger.info(
        f"Order fulfilled | ok={getattr(fulfillment_result, 'ok', None)} | "
        f"order_id={getattr(fulfillment_result, 'order_id', '')}"
    )


@executor
def log_rejection(rejector_response: AgentExecutorResponse, ctx: WorkflowContext) -> None:
    """Terminal logger for rejection runs."""
    rejector_result = rejector_response.agent_run_response.value
    logger.info(
        f"Order rejected | notified={getattr(rejector_result, 'rejection_messaging_complete', None)}"
    )


def create_workflow():
    """Construct a fresh workflow instance for each run."""
    return (
        WorkflowBuilder(name="po_pipeline_agents")
        .set_start_executor(classifier)
        .add_edge(classifier, parser, condition=should_parse)
        .add_edge(parser, retriever)
        .add_edge(retriever, decider)
        # .add_edge(retriever, fact_checker)
        # .add_edge(fact_checker, decider, condition=should_be_grounded)
        .add_edge(decider, fulfiller, condition=should_fulfill)
        .add_edge(decider, rejector, condition=should_reject)
        .add_edge(fulfiller, log_fulfillment)
        .add_edge(rejector, log_rejection)
        .build()
    )


# It's a global workflow instance template; fresh instances are created per run.
workflow = create_workflow()


async def run_till_mail_read():  # async because we'll need to await workflow.run()
    """Run the workflow repeatedly until no unread Gmail messages remain."""
    processed = 0
    
    while True:
        unread_messages = fetch_unread_emails()
        if not unread_messages:
            logger.info("Email processing complete | total_processed={}",
                        processed)
            break

        current = unread_messages[0]
        subject_preview = current.get("subject", "").strip()
        
        logger.info(
            "Email processing started | email_id={} | subject={}",
            current.get("id"),
            subject_preview or "[no subject]",
        )

        kickoff_prompt = (
            "Process the latest unread Gmail message. Classify it, "
            "then continue through parsing, resolution, and routing."
        )

        # Create a fresh workflow instance for this run (to avoid state leakage)
        workflow_instance = create_workflow()

        # Run the workflow
        logger.info("Starting workflow execution for email_id={}", current.get('id'))
        result = await workflow_instance.run(kickoff_prompt)  # await because run() is async
        logger.info("Workflow completed for email_id={}", current.get('id'))

        # After processing, mark the email as read
        mark_result = mark_email_as_read(current["id"])

        # Clear evidence to prevent leaking between workflow runs
        clear_evidence()

        processed += 1
        
        logger.info(
            "Email marked read | email_id={} | total_processed={}",
            mark_result["id"],
            processed
        )
