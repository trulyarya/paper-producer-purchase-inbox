# import asyncio
# import json
# from typing import Any
# from agent_framework.devui import serve
# from messaging.slack_human_approved_msg import request_slack_approval

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
    chat_client,
)

from agents.tool_capture import clear_evidence

from emailing.gmail_tools import (
    fetch_unread_emails,  # this is NOT the AI function get_unread_emails!
    mark_email_as_read
)

from loguru import logger  # Loguru is easier to set up than logging


# Add logger with custom formatting:
logger.add(
    sys.stdout,  # Log to standard output (console)
    level="DEBUG",  # Set log level to DEBUG (capture all messages)
    colorize=False,  # Plain output to avoid markup artifacts
    format="[WORKFLOW] {message}",
)


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


@executor
def log_fulfillment(fulfillment_response: AgentExecutorResponse, ctx: WorkflowContext) -> None:
    """Terminal logger for successful fulfillment runs."""
    fulfillment_result = fulfillment_response.agent_run_response.value
    logger.debug(
        "Fulfillment finished (ok={ok}, order_id={order_id})",
        ok=getattr(fulfillment_result, "ok", None),
        order_id=getattr(fulfillment_result, "order_id", ""),
    )


@executor
def log_rejection(rejector_response: AgentExecutorResponse, ctx: WorkflowContext) -> None:
    """Terminal logger for rejection runs."""
    rejector_result = rejector_response.agent_run_response.value
    logger.debug(
        "Rejection finished (notified={notified})",
        notified=getattr(rejector_result, "rejection_messaging_complete", None),
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


async def run_till_mail_read():
    """Run the workflow repeatedly until no unread Gmail messages remain."""
    processed = 0
    
    while True:
        unread_messages = fetch_unread_emails()
        if not unread_messages:
            print(
                "[WORKFLOW] No unread emails remaining. "
                f"Processed {processed} message(s)."
            )
            break

        current = unread_messages[0]
        subject_preview = current.get("subject", "").strip()
        print(
            "[WORKFLOW] Processing email: "
            f"{current.get('id')} — {subject_preview or '[no subject]'}"
        )

        kickoff_prompt = (
            "Process the latest unread Gmail message. Classify it, "
            "then continue through parsing, resolution, and routing."
        )

        # Create a fresh workflow instance for this run (to avoid state leakage)
        workflow_instance = create_workflow()

        # Run the workflow
        print("[WORKFLOW] Starting workflow execution...")
        result = await workflow_instance.run(kickoff_prompt)
        print(f"[WORKFLOW] ✓ Workflow completed")

        # After processing, mark the email as read
        mark_result = mark_email_as_read(current["id"])

        # Clear evidence to prevent leaking between workflow runs
        clear_evidence()

        processed += 1
        
        print(
            f"[WORKFLOW] ✓ Marked email {mark_result['id']}"
            f" as read (processed={processed})"
        )

    print("[WORKFLOW] ✓ All unread messages processed")




# if __name__ == "__main__":
#     asyncio.run(run_till_mail_read())
#
#     # Start the DevUI to visualize the workflow:
#     from agent_framework.devui import serve  
#     serve([workflow], auto_open=True)
