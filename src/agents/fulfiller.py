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
    try:
        thread_ts = post_approval_request(retrieved_po)
    except Exception as e:
        return {
            "status": "error",
            "reason": f"Failed to post to Slack: {str(e)}",
            "email_sent": "false",
        }
    
    # Step 2: Block and wait for human approval (polls Slack thread every 2s)
    channel = os.getenv("SLACK_APPROVAL_CHANNEL", "orders")  # Channel name WITHOUT #
    approved = get_approval_from_slack(
        channel=channel,
        thread_ts=thread_ts,
        timeout=60,  # 1 minute for human to respond
    )
    
    # Step 3: If approved, send confirmation email immediately
    if approved:
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
          """You are the fulfillment executor for purchase orders marked FULFILLABLE.

You receive a Decision object. Extract input_payload (the RetrievedPO) from it.

CRITICAL: You MUST execute ALL steps in order. Do NOT skip steps. Do NOT return early.

STEP 1 - Customer setup (if needed):
   • Check if customer_id equals 'NEW' or similar placeholder
   • If yes: call add_new_customer(customer_name, customer_email, customer_address)
   • Then call ingest_customers_from_airtable()
   • Continue to STEP 2

STEP 2 - Generate invoice:
   • Call generate_invoice_pdf_url(order_context=input_payload)
   • Store the returned URL string as invoice_url
   • Continue to STEP 3

STEP 3 - Request human approval and send email:
   • Call send_confirmation_email_with_approval(
       message_id=input_payload.email_id,
       invoice_url=invoice_url,
       retrieved_po=input_payload
     )
   • WAIT for the function to return (it blocks until human approves/denies in Slack)
   • Check the response dictionary's 'status' field:
     - If status == 'approved': Continue to STEP 4
     - If status == 'denied': Skip STEP 4, go to STEP 5 with ok=False
     - If status == 'error': Skip STEP 4, go to STEP 5 with ok=False

STEP 4 - Update inventory and credit (ONLY if approved in STEP 3):
   • For each item in input_payload.items:
     - Call update_inventory(ordered_qty=item.ordered_qty, product_sku=item.product_sku)
   • Call update_customer_credit(customer_id=input_payload.customer_id, order_amount=input_payload.order_total)
   • Call ingest_products_from_airtable()
   • Call ingest_customers_from_airtable()
   • Continue to STEP 5

STEP 5 - Return result:
   • Construct FulfillmentResult with:
     - ok: True ONLY if STEP 3 was approved AND STEP 4 completed successfully
     - order_id: input_payload.po_number
     - invoice_no: input_payload.po_number (use as invoice number)
   • Return the FulfillmentResult object

Do NOT return FulfillmentResult until you have executed STEPS 1-4 completely."""
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
