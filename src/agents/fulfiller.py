from typing import Any, Annotated

from agent_framework import ChatAgent, ai_function
from pydantic import BaseModel, ConfigDict, Field

from invoice.invoice_tools import generate_invoice_pdf_url
from messaging.slack_approval import post_approval_request, get_approval_from_slack

from agents.base import chat_client

from emailing.gmail_tools import respond_confirmation_email

from crm.airtable_tools import (
    update_customer_credit,
    update_inventory,
    add_new_customer,
)

from aisearch.azure_search_tools import (
    ingest_products_from_airtable,
    ingest_customers_from_airtable,
)


@ai_function
def send_confirmation_email_with_approval(
    message_id: str,
    invoice_url: str,
    retrieved_po: dict[str, Any],
) -> dict[str, str]:
    """Get human approval via Slack, then send confirmation email if approved.
    
    This function BLOCKS execution and waits for a human to approve or deny
    the order by replying in a Slack thread. If approved, it immediately sends
    the confirmation email. If denied, it returns denial status without sending.
    
    Args:
        message_id: Gmail message ID to reply to.
        invoice_url: The generated invoice URL to include in confirmation.
        retrieved_po: The enriched PO data (required for approval display).
        
    Returns:
        Dictionary with approval status and whether email was sent.
    """
    import os
    
    # Step 1: Post order to Slack and get thread timestamp
    print(f"[APPROVAL] Posting order to Slack for human review...")
    try:
        thread_ts = post_approval_request(retrieved_po)
    except Exception as e:
        return {
            "status": "error",
            "reason": f"Failed to post to Slack: {str(e)}",
            "email_sent": "false",
        }
    
    # Step 2: Block and wait for human approval (polls Slack thread every 2s)
    print(f"[APPROVAL] Waiting for human response in Slack...")
    channel = os.getenv("SLACK_APPROVAL_CHANNEL", "orders")  # Channel name WITHOUT #
    approved = get_approval_from_slack(
        channel=channel,
        thread_ts=thread_ts,
        timeout=60,  # 1 minute for human to respond
    )
    
    # Step 3: If approved, send confirmation email immediately
    if approved:
        print(f"[APPROVAL] ✓ Approved! Sending confirmation email...")
        try:
            respond_confirmation_email(
                message_id=message_id,
                pdf_url=invoice_url,
                retrieved_po=retrieved_po,
            )
            return {
                "status": "approved",
                "email_sent": "true",
            }
        except Exception as e:
            return {
                "status": "approved",
                "email_sent": "false",
                "reason": f"Approved but email failed: {str(e)}",
            }
    else:
        print(f"[APPROVAL] ✗ Denied! No confirmation email sent.")
        return {
            "status": "denied",
            "email_sent": "false",
            "reason": "Human denied approval in Slack",
        }


class FulfillmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: Annotated[
        bool,
        Field(
            description="Whether fulfillment completed successfully"
        ),
    ]
    order_id: Annotated[
        str,
        Field(
            description="The generated order ID from the CRM",
        ),
    ]
    invoice_no: Annotated[
        str,
        Field(
            description="The invoice number or document reference",
        ),
    ]


fulfiller = ChatAgent(
     chat_client=chat_client,
     name="fulfiller",
     instructions=(
          """You own the happy-path fulfillment flow for purchase orders marked FULFILLABLE.

You receive a Decision object whose input_payload is the RetrievedPO.

Follow this playbook:
1. Customer setup (if needed):
   • If customer_id is NEW (or similar), call add_new_customer(...) first.
   • Call ingest_customers_from_airtable() after adding a new customer.

2. Generate invoice:
   • Call generate_invoice_pdf_url(input_payload) to get the invoice link.

3. Request approval and send confirmation:
   • Call send_confirmation_email_with_approval(message_id, invoice_url, input_payload).
   • CRITICAL: Pass the ORIGINAL input_payload (RetrievedPO), NOT any transformed data.
   • This function will BLOCK and wait for a human to reply 'approve' or 'deny' in Slack.
   • If approved, it automatically sends the confirmation email.
   • If denied, it returns without sending.
   • Check the 'status' field in the response.

4. Update systems (only if approved):
   • Loop over items and call update_inventory(ordered_qty, product_sku).
   • Call update_customer_credit(customer_id, order_total).
   • Sync data by calling ingest_products_from_airtable() and ingest_customers_from_airtable().

Always return FulfillmentResult with ok, order_id, and invoice_no."""
     ),
     tools=[
          send_confirmation_email_with_approval,  # Approval + email combined
          add_new_customer,
          ingest_customers_from_airtable,
          generate_invoice_pdf_url,
          update_inventory,
          update_customer_credit,
          ingest_products_from_airtable,
     ],
     response_format=FulfillmentResult,
)
