from math import e
import sys
from pathlib import Path
from typing import Any

# Ensure the repository's src/ directory is importable when running as a script
# resolve() gets absolute path; parents[1] goes up two levels
PROJECT_SRC = Path(__file__).resolve().parents[1]  # this gets us to the src/ directory
sys.path.insert(0, str(PROJECT_SRC))  # add src to sys.path, index '0' means start of list

from agent_framework import (
    WorkflowBuilder,  # Builder class for constructing workflows (includes .add(), etc. methods)
    WorkflowContext,  # Controlled interface for executors to interact w workflow ecosystem
    AgentExecutorResponse,  # Response object returned by agent executors
    executor,  # Decorator converts standalone functions to FunctionExecutor instances
)

from agents import (
    classifier,
    parser,
    retriever,
    # fact_checker,
    decider,
    fulfiller,
    rejector,
)

from agents.tool_capture import clear_evidence
from safety.groundedness_check import check_agent_groundedness
from aisearch.azure_search_tools import destroy_indexes # executor to delete indexes after use
from emailing.gmail_tools import (
    # below is NOT the AI function (get_unread_emails is, which is used by the agent)!
    fetch_unread_emails,
    mark_email_as_read
)

from loguru import logger


@logger.catch  # Decorator to catch & log exceptions in the function if any occur
def should_parse(agent_response: AgentExecutorResponse) -> bool:
    """Route to parser only if email is a PO: is_po=True"""
    logger.info(
        "[FUNCTION should_parse] Checking whether the email is a Purchase Order..."
    )
    
    return getattr(agent_response.agent_run_response.value,
                   'is_po', False)


@logger.catch
def should_fulfill(agent_response: AgentExecutorResponse) -> bool:
    """Route to fulfiller if order is fulfillable: status='FULFILLABLE'"""
    logger.info(
        "[FUNCTION should_fulfill] Checking whether the order is FULFILLABLE..."
    )

    return getattr(agent_response.agent_run_response.value,
                   'status', None) == "FULFILLABLE"


@logger.catch
def should_reject(agent_response: AgentExecutorResponse) -> bool:
    """Route to rejector if order is unfulfillable: status='UNFULFILLABLE'"""
    logger.info(
        "[FUNCTION should_reject] Checking whether the order is UNFULFILLABLE..."
    )
        
    return getattr(agent_response.agent_run_response.value,
                   'status', None) == "UNFULFILLABLE"


@logger.catch
def should_be_grounded(groundedness_response: AgentExecutorResponse) -> bool:
    """Route to decider if groundedness check passes.
    If False, workflow terminates and logs the failure."""
    
    # Read groundedness metadata from additional_properties (not from .value!)
    # The check_agent_groundedness executor attaches metadata to AgentRunResponse.additional_properties
    additional_props = groundedness_response.agent_run_response.additional_properties or {}
    is_grounded = additional_props.get('is_grounded_result', False)
    
    # Log failure case before returning
    if not is_grounded:
        logger.warning(
            "Groundedness check FAILED | score={} | reason={}",
            additional_props.get('groundedness_score', 0),
            additional_props.get('groundedness_reason', 'No reason provided')
        )
    else:
        logger.info("Groundedness check PASSED.")
    
    return is_grounded


@executor  # Decorator to make this function an executor in the workflow graph
@logger.catch
async def log_fulfillment(
    fulfillment_response: AgentExecutorResponse,
    ctx: WorkflowContext[AgentExecutorResponse],
) -> None:
    """Terminal logger for successful fulfillment runs."""
    fulfillment_result = fulfillment_response.agent_run_response.value
    
    logger.info(
        f"Order fulfilled | ok={getattr(fulfillment_result, 'ok', None)} | "
        f"order_id={getattr(fulfillment_result, 'order_id', '')}"
    )
    
    # Forward the same response so downstream cleanup executes regardless of branch
    await ctx.send_message(fulfillment_response)


@executor
@logger.catch
async def log_rejection(
    rejector_response: AgentExecutorResponse,
    ctx: WorkflowContext[AgentExecutorResponse],
) -> None:
    """Terminal logger for rejection runs."""
    rejector_result = rejector_response.agent_run_response.value
    
    logger.info(
        f"Order rejected | notified="
        f"{getattr(rejector_result, 'rejection_messaging_complete', None)}"
    )
    
    await ctx.send_message(rejector_response)


@logger.catch
def create_workflow():
    """Construct a fresh workflow instance for each run."""
    return (
        WorkflowBuilder(name="po_pipeline_agents")
        .set_start_executor(classifier)
        .add_edge(classifier, parser, condition=should_parse)
        .add_edge(parser, retriever)
        .add_edge(retriever, check_agent_groundedness)
        .add_edge(check_agent_groundedness, decider, condition=should_be_grounded)
        .add_edge(decider, fulfiller, condition=should_fulfill)
        .add_chain([fulfiller, log_fulfillment, destroy_indexes])
        .add_edge(decider, rejector, condition=should_reject)
        .add_chain([rejector, log_rejection, destroy_indexes])
        .build()
    )


# It's a global workflow instance template; fresh instances are created per run.
workflow = create_workflow()


@logger.catch
async def run_till_mail_read():  # async cuz we'll need to await workflow.run()
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
        
        # result = await workflow_instance.run(kickoff_prompt)
        await workflow_instance.run(kickoff_prompt)  # await cuz run() is async
        
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
