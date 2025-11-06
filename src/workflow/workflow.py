import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Ensure the repository's src/ directory is importable when running as a script.
PROJECT_SRC = Path(__file__).resolve().parents[1]
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from agent_framework import WorkflowBuilder, ChatMessage
from agent_framework.devui import serve
from agents import (
    classifier,
    decider,
    fulfiller,
    parser,
    rejector,
    retriever,
)
from emailing.gmail_tools import (
    fetch_unread_emails,  # this is NOT the AI function get_unread_emails!
    mark_email_as_read
)
# from messaging.slack_human_approved_msg import request_slack_approval


def should_parse(resp) -> bool:
    """Route to parser only if email is a PO."""
    return resp.agent_run_response.value.is_po


def should_fulfill(resp) -> bool:
    """Route to fulfiller if order is fulfillable."""
    return resp.agent_run_response.value.status == "FULFILLABLE"


def should_reject(resp) -> bool:
    """Route to rejector if order is unfulfillable."""
    return resp.agent_run_response.value.status == "UNFULFILLABLE"


def create_workflow():
    """Construct a fresh workflow instance for each run."""
    return (
        WorkflowBuilder(name="po_pipeline_agents")
        .set_start_executor(classifier)
        .add_edge(classifier, parser, condition=should_parse)
        .add_edge(parser, retriever)
        .add_edge(retriever, decider)
        .add_edge(decider, fulfiller, condition=should_fulfill)
        .add_edge(decider, rejector, condition=should_reject)
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

        processed += 1
        
        print(
            f"[WORKFLOW] ✓ Marked email {mark_result['id']}"
            f" as read (processed={processed})"
        )

    print("[WORKFLOW] ✓ All unread messages processed")


if __name__ == "__main__":
    asyncio.run(run_till_mail_read())
    # serve([workflow], auto_open=True)
