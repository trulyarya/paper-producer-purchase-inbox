from pathlib import Path
from re import A
from typing import Any, Annotated

from agent_framework import ChatAgent, ai_function
from pydantic import BaseModel, ConfigDict, Field

from invoice.invoice_tools import generate_invoice_pdf_url
from messaging.slack_msg_sender import post_slack_message

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



# @ai_function
# def update_inventory(order_lines: list[dict[str, Any]]) -> dict[str, Any]:
#     """Deduct ordered quantities from inventory."""
#     return {
#         "status": "queued",
#         "lines_processed": len(order_lines),
#     }


# @ai_function
# def update_customer_credit(customer_id: str, order_total: float) -> dict[str, Any]:
#     """Adjust customer credit exposure."""
#     return {
#         "customer_id": customer_id,
#         "order_total": order_total,
#         "status": "queued",
#     }


# @ai_function
# def add_order_to_crm(
#     resolved_po: dict[str, Any],
#     invoice_pdf_url: str | None = None,
# ) -> dict[str, Any]:
#     """Persist order details to CRM."""
#     order_id = f"PO-{resolved_po.get('customer_id', 'UNKNOWN')}-{hash(str(resolved_po)) % 10000:04d}"
#     return {
#         "order_id": order_id,
#         "invoice_url": invoice_pdf_url,
#         "status": "created",
#     }


@ai_function
def generate_invoice(resolved_po: dict[str, Any]) -> str:
    """Generate invoice PDF and return its URL."""
    # Resolve template relative to this file so execution works from any CWD.
    # This translates to 'src/invoice/invoice_template.html' for template file
    html_template = (
        Path(__file__).resolve().parent.parent / "invoice" / "invoice_template.html"
    )

    invoice_pdf_url = generate_invoice_pdf_url(
        html_template=html_template,
        order_context=resolved_po,
    )

    return invoice_pdf_url


@ai_function
def send_slack_notification(
    resolved_po: dict[str, Any],
    order_id: str,
    invoice_url: str | None = None,
) -> dict[str, Any]:
    """Send a Slack notification to the operations channel with order details."""
    customer_name = resolved_po.get("customer_name", "Unknown Customer")
    order_total = resolved_po.get("total", 0.0)
    items = resolved_po.get("items", [])
    item_count = len(items)
    order_items = [
        f"{item['qty']}x {item['name']} ({item['sku']}) @ €{item['price']:.2f}"
        for item in items
    ]
    fields = {
        "Customer": customer_name,
        "Order ID": order_id,
        "Total": f"€{order_total:.2f}",
        "Items": str(item_count),
    }
    post_slack_message(
        fields=fields,
        order_items=order_items,
        invoice_url=invoice_url,
        agent_name="PO Automation Agent",
    )
    return {
        "status": "sent",
        "customer": customer_name,
        "order_id": order_id,
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
        """You're an order fulfillment sub-agent responsible for processing validated purchase orders.

You receive a resolved_po dictionary containing customer details, order items, and totals.

Execute fulfillment in this sequence:

1. update_inventory(order_lines) - Deduct ordered quantities from inventory stock levels
2. update_customer_credit(customer_id, order_total) - Adjust customer's credit exposure in CRM
3. ingest_products_from_airtable() - Sync updated inventory to Azure AI Search indexes
4. ingest_customers_from_airtable() - Sync updated customer data to Azure AI Search indexes
5. generate_invoice(resolved_po) - Generate invoice PDF and return its URL
6. respond_confirmation_email() - Send order confirmation email to customer with invoice attached
7. send_slack_notification(resolved_po, order_id, invoice_url) - Notify operations team in Slack

Notes:
- If customer doesn't exist, call add_new_customer() before processing, then sync with ingest_customers_from_airtable()
- Steps 3-4 ensure Azure AI Search indexes stay synchronized with CRM changes
- The generate_invoice() function returns the invoice_pdf_url string
- Use the invoice URL from step 5 when calling send_slack_notification()
- Extract order_id from CRM operations or generate from resolved_po data
- Extract invoice_no from the invoice generation process

Return FulfillmentResult with:
- ok: true if all steps completed successfully
- order_id: the CRM order identifier
- invoice_no: the invoice document reference number
"""
    ),
    tools=[
        update_inventory,
        update_customer_credit,
        add_new_customer,
        ingest_products_from_airtable,
        ingest_customers_from_airtable,
        generate_invoice,
        respond_confirmation_email,
        send_slack_notification,
    ],
    response_format=FulfillmentResult,
)
