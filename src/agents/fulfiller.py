from pathlib import Path
from typing import Any, Annotated

from agent_framework import ChatAgent, ai_function
from pydantic import BaseModel, ConfigDict, Field

from invoice.invoice_tools import generate_invoice_pdf_url
from messaging.slack_msg_sender import post_slack_message

from agents.base import chat_client


@ai_function
def update_inventory(order_lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Deduct ordered quantities from inventory."""
    return {
        "status": "queued",
        "lines_processed": len(order_lines),
    }


@ai_function
def update_customer_credit(customer_id: str, order_total: float) -> dict[str, Any]:
    """Adjust customer credit exposure."""
    return {
        "customer_id": customer_id,
        "order_total": order_total,
        "status": "queued",
    }


@ai_function
def add_order_to_crm(
    resolved_po: dict[str, Any],
    invoice_pdf_url: str | None = None,
) -> dict[str, Any]:
    """Persist order details to CRM."""
    order_id = f"PO-{resolved_po.get('customer_id', 'UNKNOWN')}-{hash(str(resolved_po)) % 10000:04d}"
    return {
        "order_id": order_id,
        "invoice_url": invoice_pdf_url,
        "status": "created",
    }


@ai_function
def generate_invoice(resolved_po: dict[str, Any]) -> str:
    """Generate invoice PDF and return its URL."""
    html_template = Path("src/invoice/invoice_template.html")
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
    ok: Annotated[bool, Field(
        description="Whether fulfillment completed successfully")]
    order_id: Annotated[str, Field(
        description="The generated order ID from the CRM")]
    invoice_no: Annotated[str, Field(
        description="The invoice number or document reference")]


fulfiller = ChatAgent(
    chat_client=chat_client,
    name="fulfiller",
    instructions=("""You're an order fulfillment agent. 

The ResolvedPO already contains all customer and total information.

Fulfill the order by calling tools in sequence:
1. update_inventory() - deduct items from stock
2. update_customer_credit() - adjust customer credit exposure
3. generate_invoice_pdf() - create the invoice (returns URL)
4. add_order_to_crm() - persist order (returns order_id)
5. compose_fulfillment_email() - draft confirmation email
6. respond_confirmation_email() - send email with invoice attached
7. send_slack_notification() - notify ops team (pass invoice_url from step 3)

Return FulfillmentResult with ok=true, order_id, and invoice_no.
"""
                  ),
    tools=[
        update_inventory,
        update_customer_credit,
        add_order_to_crm,
        generate_invoice,
        # compose_fulfillment_email,
        # respond_confirmation_email,
        send_slack_notification,
    ],
    response_format=FulfillmentResult,
)
