import asyncio
from typing import Annotated, Literal, Any
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, computed_field

from dotenv import load_dotenv

from agent_framework.observability import setup_observability
from agent_framework import WorkflowBuilder, ChatAgent, ai_function
# azure openai chat completion client class
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from agent_framework.devui import serve

from email.gmail_tools import fetch_unread_emails, mark_email_as_read
from messaging.slack_msg_sender import post_slack_message
from invoice.invoice_tools import generate_invoice_pdf_url
# from crm.airtable_tools import   # placeholder imports

load_dotenv()  # load env vars from .env if present
setup_observability()

# =========================
# 1) Pydantic models
# =========================

# -----------------------------------------------------
# Email model: used in classifier and parser agents
# -----------------------------------------------------


class Email(BaseModel):
    model_config = ConfigDict(extra="forbid")  # forbid extra fields
    id: Annotated[str, Field(description="Gmail message ID for this email")]
    subject: Annotated[str, Field(
        description="Email subject line as received")]
    sender: Annotated[str, Field(description="Email address of the sender")]
    body: Annotated[str, Field(
        description="Plaintext body content of the email")]


class ClassifiedEmail(BaseModel):
    email: Annotated[Email, Field(
        description="The email instance being evaluated")]
    is_po: Annotated[bool, Field(
        description="True if the email is classified as a purchase order")]
    reason: Annotated[str, Field(
        description="Brief classifier rationale supporting the decision")]


# -----------------------------------------------------
# Parsed PO model: used in  parser and resolver agents
# -----------------------------------------------------

class ProductLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_sku: Annotated[str, Field(
        description="Line item product-SKU or identifier from customer's PO email")]
    product_name: Annotated[str, Field(
        description="Line item product name or description from customer's PO email")]
    ordered_qty: Annotated[int, Field(
        gt=0, strict=True, description="Quantity requested for the line item from PO")]


class ParsedPO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_id: Annotated[str, Field(
        description="ID of the email this parsed purchase order came from")]
    customer_email: Annotated[str, Field(
        description="Customer email address where the PO email was sent from, extracted")]
    customer_company_name: Annotated[str, Field(
        description="Customer or company name extracted from the PO email")]
    customer_billing_address: Annotated[str, Field(
        description="Billing address extracted for the customer from the PO email")]
    customer_shipping_address: Annotated[str, Field(
        description="Shipping address extracted for the customer from the PO email")]
    line_items: Annotated[list[ProductLineItem], Field(
        description="List of individual line items parsed from the purchase order")]


# -----------------------------------------------------
# Resolved PO model: used in resolver and decider agents
# -----------------------------------------------------

class ResolvedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matched_customer_id: Annotated[
        str,
        Field(
            description="Resolved customer identifier from CRM (Customers)",
        ),
    ]
    matched_customer_name: Annotated[
        str,
        Field(
            description="Resolved customer name from CRM (Customers)",
        ),
    ]
    matched_customer_address: Annotated[
        str,
        Field(
            description="Resolved customer address from CRM (Customers)",
        ),
    ]
    matched_product_sku: Annotated[
        str,
        Field(
            description="Matched product SKU identifier from catalog (Products) "
            "through similarity search",
        ),
    ]
    matched_product_name: Annotated[
        str,
        Field(
            description="Matched product name or title from catalog (Products) "
            "through similarity search",
        )
    ]
    ordered_qty: Annotated[
        int,
        Field(
            gt=0,
            strict=True,
            description="Quantity ordered",
        ),
    ]
    price: Annotated[
        float,
        Field(
            ge=0,
            strict=True,
            description="Unit price in EUR",
        ),
    ]
    vat_rate: Annotated[
        float,
        Field(
            default=0.19,
            description="VAT rate (default 19% for Germany)",
        ),
    ]
    product_availability: Annotated[
        bool,
        Field(
            description="Whether the item is in stock and available: "
            "True only if Qty Available >= ordered_qty",
        ),
    ]

    @computed_field  # Derived field for line item subtotal
    @property        # Line item subtotal (ordered_qty * price)
    def line_item_subtotal(self) -> Annotated[
        float,
        Field(
            description="Line item subtotal for each SKU (ordered_qty * price)",
        ),
    ]:
        return self.ordered_qty * self.price


class ResolvedPO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_id: Annotated[str, Field(
        description="Gmail message ID of the original purchase order email")]
    customer_id: Annotated[str, Field(
        description="Customer identifier or account number")]
    customer_name: Annotated[str, Field(
        description="Customer's business or contact name")]
    customer_credit_ok: Annotated[bool, Field(
        description="Whether customer has sufficient credit to fulfill this order")]
    items: Annotated[list[ResolvedItem], Field(
        description="list of resolved order line items")]

    @computed_field
    @property
    def tax(self) -> Annotated[
        float,
        Field(
            ge=0,
            strict=True,
            description="Calculated sales tax (sum of line subtotal * VAT rate)",
        ),
    ]:
        return sum(item.line_item_subtotal * item.vat_rate for item in self.items)

    @computed_field
    @property
    def shipping(self) -> Annotated[
            float,
            Field(ge=0, strict=True, description="Flat shipping fee (€25 if subtotal > 0)")]:
        return 25.0 if self.subtotal > 0 else 0.0

    @computed_field
    @property
    def subtotal(self) -> Annotated[float, Field(ge=0, strict=True, description="Subtotal of all line items before tax and shipping")]:
        return sum(item.line_item_subtotal for item in self.items)

    @computed_field
    @property
    def order_total(self) -> Annotated[float, Field(ge=0, strict=True, description="Final total: subtotal + tax + shipping")]:
        return self.subtotal + self.tax + self.shipping


# -----------------------------------------------------
# Decision model: used in decider agent
# -----------------------------------------------------

class Decision(BaseModel):
    status: Annotated[Literal["FULFILLABLE", "UNFULFILLABLE"],
                      Field(description="Whether the order can be fulfilled")]
    reason: Annotated[str, Field(
        description="Explanation for the fulfillment decision")]
    payload: Annotated[ResolvedPO, Field(
        description="The original ResolvedPO being evaluated")]


# -----------------------------------------------------
# Fulfillment result model: used in fulfiller agent
# -----------------------------------------------------

class FulfillmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: Annotated[bool, Field(
        description="Whether fulfillment completed successfully")]
    order_id: Annotated[str, Field(
        description="The generated order ID from the CRM")]
    invoice_no: Annotated[str, Field(
        description="The invoice number or document reference")]


# -----------------------------------------------------
# Reject result model: used in rejector agent
# -----------------------------------------------------

class RejectResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: Annotated[bool, Field(
        description="Whether the rejection was handled successfully")]


# ==========================================================================================
# 2) Tool (function) implementations
# ==========================================================================================

# @ai_function
# def gmail_grabber() -> list[dict[str, str]]:
#     """Pull unread Gmail messages."""
#     service = authenticate_gmail()
#     return fetch_unread_emails(service)


# @ai_function
# def clean_email_payload(email: dict[str, Any]) -> dict[str, Any]:
#     """Lightly normalize email text so downstream parsing is easier."""
#     body = email.get("body", "")
#     cleaned_lines = [line.strip() for line in body.splitlines() if line.strip()]
#     cleaned_body = "\n".join(cleaned_lines)
#     return {
#         **email,
#         "body": cleaned_body,
#         "body_original": body,
#     }


@ai_function
def prepare_sku_candidates(payload: dict[str, Any], top_k: int = 5) -> dict[str, Any]:
    """Return placeholder SKU candidates for each order line."""
    order = payload.get("purchase_order", {})
    lines = order.get("order_lines", [])
    return {
        "purchase_order": order,
        "line_candidates": [
            {
                "line_index": idx,
                "candidates": [
                    {
                        "sku": f"SKU-{idx}-{i}",
                        "title": f"Candidate {i}",
                        "description": "Placeholder candidate generated by prepare_sku_candidates.",
                        "similarity_score": max(0.1, 1.0 - 0.1 * i),
                    }
                    for i in range(min(top_k, 3))
                ],
            }
            for idx, _ in enumerate(lines)
        ],
    }


@ai_function
def check_credit(customer_name: str, order_total: float) -> dict[str, Any]:
    """Mock credit check against static limits."""
    credit_limit = 10000.0
    open_ar = 2500.0
    available_credit = credit_limit - open_ar
    approved = order_total <= available_credit
    return {
        "customer_name": customer_name,
        "order_total": order_total,
        "credit_limit": credit_limit,
        "open_ar": open_ar,
        "available_credit": max(0.0, available_credit - order_total),
        "approved": approved,
        "reason": "Within credit limits" if approved else "Exceeds available credit",
    }


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
    """Persist order details to CRM.

    Args:
        resolved_po: The complete ResolvedPO with customer and order details
        invoice_pdf_url: Optional URL to the generated invoice PDF
    Returns:
        dict: Contains generated order_id and status
    """
    order_id = f"PO-{resolved_po.get('customer_id', 'UNKNOWN')}-{hash(str(resolved_po)) % 10000:04d}"
    return {
        "order_id": order_id,
        "invoice_url": invoice_pdf_url,
        "status": "created",
    }


@ai_function
def generate_invoice(resolved_po: dict[str, Any]) -> str:
    """Generate invoice PDF and return its URL.

    Args:
        resolved_po: The complete ResolvedPO with all order details
    Returns:
        str: Public URL to the generated invoice PDF
    """

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
    """Send a Slack notification to the operations channel with order details.

    Args:
        resolved_po: The ResolvedPO dict containing customer_name, items, and totals
        order_id: The order ID from add_order_to_crm
        invoice_url: Optional URL to the invoice PDF for quick access
    """
    customer_name = resolved_po.get("customer_name", "Unknown Customer")
    order_total = resolved_po.get("total", 0.0)

    # Build item list from resolved_po items
    items = resolved_po.get("items", [])
    item_count = len(items)
    order_items = [
        f"{item['qty']}x {item['name']} ({item['sku']}) @ €{item['price']:.2f}"
        for item in items
    ]

    # Build Slack fields
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


# =========================
# 2) Build agents, each returns a Pydantic model
#    via response_format
# =========================

chat_client = AzureOpenAIChatClient(
    credential=AzureCliCredential())  # supply your config

classifier = ChatAgent(
    chat_client=chat_client,
    name="classifier",
    instructions=(
        "You are the inbox triage specialist. Call `gmail_grabber()` exactly once to fetch unread Gmail messages. "
        "Select the first unread message returned and decide if it is a purchase order. "
        "Return a ClassifiedEmail JSON matching the response schema, embedding the chosen email under `email`. "
        "If the message is not a purchase order, set `is_po` to false and explain briefly in `reason`. "
        "Output only the JSON object—no additional prose."
    ),
    tools=[
        fetch_unread_emails,
    ],
    response_format=ClassifiedEmail,
)

parser = ChatAgent(
    chat_client=chat_client,
    name="parser",
    instructions=(
        "Parse the email selected by the classifier into structured purchase order fields. "
        "Use the `email` object from the classifier's latest response as your source material. "
        "Call `clean_email_payload` when normalization helps. "
        "Return a ParsedPO JSON that matches the schema, inferring reasonable defaults as needed."
    ),
    tools=[
        # clean_email_payload
    ],
    response_format=ParsedPO,
)

resolver = ChatAgent(
    chat_client=chat_client,
    name="resolver",
    instructions=(
        "Resolve the ParsedPO against search and CRM. "
        "For each line item, find the SKU, name, unit price, VAT rate, and availability. "
        "Resolve or create the customer. Call check_credit with the order total you compute from the resolved line subtotals, VAT, and flat shipping (€25 whenever the subtotal is positive). "
        "Return a ResolvedPO JSON with the customer fields and resolved items only; tax, shipping, subtotal, and total are computed automatically."
    ),
    tools=[
        check_credit,
    ],
    response_format=ResolvedPO,
)

decider = ChatAgent(
    chat_client=chat_client,
    name="decider",
    instructions=(
        "Given a ResolvedPO, decide if it is fulfillable. "
        "If any item is unavailable or credit is insufficient, mark UNFULFILLABLE and set reason. "
        "Otherwise mark FULFILLABLE. "
        "Return a Decision JSON that matches the schema."
    ),
    tools=[],  # No tools needed - all data is in ResolvedPO
    response_format=Decision,
)

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

rejector = ChatAgent(
    chat_client=chat_client,
    name="rejector",
    instructions=(
        "The order cannot be fulfilled. Compose a clear, professional email reply explaining why "
        "(credit issues, unavailable items, etc.) and what the customer should do next. "
        "Send the reply via respond_unfulfillable_email(). Optionally notify the ops team via Slack. "
        "Return RejectResult with ok=true when done."
    ),
    tools=[
        # respond_unfulfillable_email,
        send_slack_notification
    ],
    response_format=RejectResult,
)

# =========================
# 3) Workflow with conditional routing
# =========================


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


# =========================
# 4) Poll Gmail and feed emails into the graph
# =========================

async def run_till_mail_read():
    """Run the workflow repeatedly until no unread Gmail messages remain.
    This is useful for development and testing to process the entire inbox.

    Each iteration:
    - Fetches unread emails
    - Processes the first unread email through the workflow
    - Marks the email as read after processing
    - Logs key events and progress
    """

    processed = 0

    # Loop until inbox is empty
    while True:
        unread_messages = fetch_unread_emails()  # fetch unread emails
        if not unread_messages:
            print(
                f"[WORKFLOW] No unread emails remaining. Processed {processed} message(s).")
            break

        current = unread_messages[0]  # pick the first unread email
        # brief subject for logging
        subject_preview = current.get("subject", "").strip()
        print(
            f"[WORKFLOW] Processing email {current.get('id')} — {subject_preview or '[no subject]'}")

        kickoff_prompt = (
            "Process the latest unread Gmail message. "
            "Classify it, then continue through parsing, resolution, and routing."
        )

        workflow_instance = create_workflow()  # fresh workflow instance per email

        # Stream the workflow execution and log key events
        async for event in workflow_instance.run_stream(kickoff_prompt):
            # Only log important events
            if not isinstance(event, type(event)) or 'Update' not in type(event).__name__:
                print(f"[WORKFLOW] {type(event).__name__}")

        # After processing, mark the email as read
        mark_result = mark_email_as_read(current["id"])

        # respond_confirmation_email(
        #     message_id=current["id"],
        #     reply_body="Thank you for your purchase order. We have received it and will process it shortly.",
        #     pdf_path=None,
        # )

        processed += 1  # count of processed emails
        print(
            f"[WORKFLOW] ✓ Marked email {mark_result['id']} as read (processed={processed})")

    print("[WORKFLOW] ✓ All unread messages processed")


if __name__ == "__main__":
    # For development: process inbox until no unread messages remain
    # asyncio.run(run_till_mail_read())

    # For UI inspection: uncomment this instead
    serve([workflow], auto_open=True)
