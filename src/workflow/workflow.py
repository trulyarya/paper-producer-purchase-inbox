import asyncio

from agent_framework import WorkflowBuilder
from agent_framework.devui import serve

from agents import (
    classifier,
    decider,
    fulfiller,
    parser,
    rejector,
    resolver,
)
from emailing.gmail_tools import fetch_unread_emails, mark_email_as_read


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
        .add_edge(parser, resolver)
        .add_edge(resolver, decider)
        .add_edge(decider, fulfiller, condition=should_fulfill)
        .add_edge(decider, rejector, condition=should_reject)
        .build()
    )


workflow = create_workflow()


async def run_till_mail_read():
    """Run the workflow repeatedly until no unread Gmail messages remain."""
    processed = 0
    while True:
        unread_messages = fetch_unread_emails()
        if not unread_messages:
            print(
                f"[WORKFLOW] No unread emails remaining. Processed {processed} message(s).")
            break

        current = unread_messages[0]
        subject_preview = current.get("subject", "").strip()
        print(
            f"[WORKFLOW] Processing email {current.get('id')} — {subject_preview or '[no subject]'}"
        )

        kickoff_prompt = (
            "Process the latest unread Gmail message. "
            "Classify it, then continue through parsing, resolution, and routing."
        )

        workflow_instance = create_workflow()

        async for event in workflow_instance.run_stream(kickoff_prompt):
            if not isinstance(event, type(event)) or "Update" not in type(event).__name__:
                print(f"[WORKFLOW] {type(event).__name__}")

        mark_result = mark_email_as_read(current["id"])
        processed += 1
        print(
            f"[WORKFLOW] ✓ Marked email {mark_result['id']} as read (processed={processed})"
        )

    print("[WORKFLOW] ✓ All unread messages processed")


if __name__ == "__main__":
    # asyncio.run(run_till_mail_read())
    serve([workflow], auto_open=True)
