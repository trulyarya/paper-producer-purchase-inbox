import asyncio
from typing import Annotated, List, Literal, Any
from pydantic import BaseModel, ConfigDict, Field, computed_field
from dotenv import load_dotenv

from agent_framework.observability import setup_observability
from agent_framework import WorkflowBuilder, ChatAgent, ai_function  # your framework
from agent_framework.azure import AzureOpenAIChatClient  # or your chat client
from azure.identity import AzureCliCredential
from agent_framework.devui import serve

from src.email.gmail_grabber import authenticate_gmail, fetch_unread_emails, mark_email_as_read, reply_to_email
from src.messaging.slack_msg_sender import post_slack_message


load_dotenv()  # load env vars from .env if present
setup_observability()

# =========================
# 1) Pydantic models
# =========================

# -----------------------------------------------------   
# Email model: used in classifier and parser agents
# -----------------------------------------------------

class Email(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    subject: str
    sender: str
    body: str

class ClassifiedEmail(BaseModel):
    email: Email
    is_po: bool
    reason: str


# -----------------------------------------------------   
# Parsed PO model: used in  parser and resolver agents
# -----------------------------------------------------

class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_or_name: str
    qty: Annotated[int, Field(gt=0, strict=True)]

class ParsedPO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_id: str
    customer_name: str
    customer_address: str
    line_items: List[LineItem]


# -----------------------------------------------------   
# Resolved PO model: used in resolver and decider agents
# -----------------------------------------------------

class ResolvedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: Annotated[str, Field(description="Product SKU identifier")]
    name: Annotated[str, Field(description="Product name or description")]
    qty: Annotated[int, Field(gt=0, strict=True, description="Quantity ordered")]
    price: Annotated[float, Field(ge=0, strict=True, description="Unit price in USD")]
    available: Annotated[bool, Field(description="Whether the item is in stock and available")]
    subtotal: Annotated[float, Field(description="Line item subtotal (qty * price)")] = Field(default_factory=lambda self: self.qty * self.price)


class ResolvedPO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_id: Annotated[str, Field(description="Gmail message ID of the original purchase order email")]
    customer_id: Annotated[str, Field(description="Customer identifier or account number")]
    customer_name: Annotated[str, Field(description="Customer's business or contact name")]
    customer_credit_ok: Annotated[bool, Field(description="Whether customer has sufficient credit to fulfill this order")]
    items: Annotated[List[ResolvedItem], Field(description="List of resolved order line items")]
    tax: Annotated[float, Field(ge=0, strict=True, description="Calculated sales tax (8% of subtotal)")]
    shipping: Annotated[float, Field(ge=0, strict=True, description="Flat shipping fee ($25 if subtotal > 0)")]
    total: Annotated[float, Field(ge=0, strict=True, description="Final total: subtotal + tax + shipping")]


# -----------------------------------------------------   
# Decision model: used in decider agent
# -----------------------------------------------------

class Decision(BaseModel):
    status: Annotated[Literal["FULFILLABLE", "UNFULFILLABLE"], Field(description="Whether the order can be fulfilled")]
    reason: Annotated[str, Field(description="Explanation for the fulfillment decision")]
    payload: Annotated[ResolvedPO, Field(description="The original ResolvedPO being evaluated")]


# -----------------------------------------------------   
# Fulfillment result model: used in fulfiller agent
# -----------------------------------------------------

class FulfillmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: Annotated[bool, Field(description="Whether fulfillment completed successfully")]
    order_id: Annotated[str, Field(description="The generated order ID from the CRM")]
    invoice_no: Annotated[str, Field(description="The invoice number or document reference")]


# -----------------------------------------------------   
# Reject result model: used in rejector agent
# -----------------------------------------------------

class RejectResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: Annotated[bool, Field(description="Whether the rejection was handled successfully")]




# ==========================
# 2) Tool (function) implementations
# =========================

@ai_function
def gmail_grabber() -> list[dict[str, str]]:
    """Pull unread Gmail messages."""
    service = authenticate_gmail()
    return fetch_unread_emails(service)


@ai_function
def clean_email_payload(email: dict[str, Any]) -> dict[str, Any]:
    """Lightly normalize email text so downstream parsing is easier."""
    body = email.get("body", "")
    cleaned_lines = [line.strip() for line in body.splitlines() if line.strip()]
    cleaned_body = "\n".join(cleaned_lines)
    return {
        **email,
        "body": cleaned_body,
        "body_original": body,
    }


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
def calculate_totals(purchase_data: dict[str, Any] | list[dict[str, Any]]) -> dict[str, float]:
    """Compute basic totals from purchase data.
    
    Accepts either:
    - A list of items directly
    - A dict with 'order_lines' or 'items' key
    
    Each item should have:
    - qty/quantity: number of items
    - price/unit_price: price per item
    """
    # Extract the list of items
    if isinstance(purchase_data, list):
        lines = purchase_data
    else:
        lines = purchase_data.get("items") or purchase_data.get("order_lines", [])
    
    subtotal = 0.0
    for line in lines:
        # Handle both 'qty' and 'quantity' field names
        qty = float(line.get("qty") or line.get("quantity", 0))
        # Handle both 'price' and 'unit_price' field names
        unit_price = float(line.get("price") or line.get("unit_price", 0))
        # Use pre-calculated line_total if available, otherwise compute it
        line_total = line.get("line_total")
        subtotal += float(line_total) if line_total is not None else qty * unit_price
    
    tax = round(subtotal * 0.08, 2)
    shipping = 25.0 if subtotal else 0.0
    total = round(subtotal + tax + shipping, 2)
    
    return {
        "subtotal": round(subtotal, 2),
        "tax": tax,
        "shipping": shipping,
        "total": total,
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
    """
    order_id = f"PO-{resolved_po.get('customer_id', 'UNKNOWN')}-{hash(str(resolved_po)) % 10000:04d}"
    return {
        "order_id": order_id,
        "invoice_url": invoice_pdf_url,
        "status": "created",
    }


@ai_function
def generate_invoice_pdf(resolved_po: dict[str, Any]) -> str:
    """Generate invoice PDF and return its URL.
    
    Args:
        resolved_po: The complete ResolvedPO with all order details
    """
    customer_id = resolved_po.get("customer_id", "unknown").replace(" ", "_")
    order_id_hash = hash(str(resolved_po)) % 10000
    return f"https://storage.example.com/invoices/{customer_id}_{order_id_hash:04d}.pdf"


@ai_function
def compose_fulfillment_email(resolved_po: dict[str, Any]) -> str:
    """Compose a fulfillment confirmation email body.
    
    Args:
        resolved_po: The complete ResolvedPO with customer and order details
    """
    customer_name = resolved_po.get("customer_name", "Valued Customer")
    total = resolved_po.get("total", 0.0)
    item_count = len(resolved_po.get("items", []))
    
    return (
        f"Hello {customer_name},\n\n"
        f"Your purchase order has been confirmed! "
        f"We're processing {item_count} item(s) with a total of ${total:.2f}.\n\n"
        "We'll notify you once your order ships.\n\n"
        "Best regards,\nPaperCo Operations"
    )


@ai_function
def send_email_reply(thread_id: str, body: str, attachment_url: str | None = None) -> dict[str, Any]:
    """Send an email reply with optional attachment."""
    reply_to_email()
    return {
        "status": "sent",
        "thread_id": thread_id,
        "attachment_url": attachment_url,
        "preview": body[:120],
    }


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
        f"{item['qty']}x {item['name']} ({item['sku']}) @ ${item['price']:.2f}"
        for item in items
    ]
    
    # Build Slack fields
    fields = {
        "Customer": customer_name,
        "Order ID": order_id,
        "Total": f"${order_total:.2f}",
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

chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())  # supply your config

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
    tools=[gmail_grabber],
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
    tools=[clean_email_payload],
    response_format=ParsedPO,
)

resolver = ChatAgent(
    chat_client=chat_client,
    name="resolver",
    instructions=(
        "Resolve the ParsedPO against search and CRM. "
        "For each line item, find the SKU, name, unit price, and availability. "
        "Resolve or create the customer and check credit. "
        "Call calculate_totals() with the resolved items to get subtotal, tax, shipping, and total. "
        "Return a ResolvedPO JSON that includes customer_name, all resolved items, and all calculated totals."
    ),
    tools=[calculate_totals, check_credit],
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
6. reply_to_email() - send email with invoice attached
7. send_slack_notification() - notify ops team (pass invoice_url from step 3)

Return FulfillmentResult with ok=true, order_id, and invoice_no.
"""
    ),
    tools=[
        update_inventory,
        update_customer_credit,
        add_order_to_crm,
        generate_invoice_pdf,
        compose_fulfillment_email,
        reply_to_email,
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
        "Send the reply via send_email_reply(). Optionally notify the ops team via Slack. "
        "Return RejectResult with ok=true when done."
    ),
    tools=[send_email_reply, send_slack_notification],
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
        unread_messages = gmail_grabber() # fetch unread emails
        if not unread_messages:
            print(f"[WORKFLOW] No unread emails remaining. Processed {processed} message(s).")
            break

        current = unread_messages[0] # pick the first unread email
        subject_preview = current.get("subject", "").strip() # brief subject for logging
        print(f"[WORKFLOW] Processing email {current.get('id')} — {subject_preview or '[no subject]'}")

        kickoff_prompt = (
            "Process the latest unread Gmail message. "
            "Classify it, then continue through parsing, resolution, and routing."
        )

        workflow_instance = create_workflow() # fresh workflow instance per email

        # Stream the workflow execution and log key events
        async for event in workflow_instance.run_stream(kickoff_prompt):
            # Only log important events
            if not isinstance(event, type(event)) or 'Update' not in type(event).__name__:
                print(f"[WORKFLOW] {type(event).__name__}")

        # After processing, mark the email as read
        mark_result = mark_email_as_read(current["id"])
        
        # reply_to_email(
        #     message_id=current["id"],
        #     reply_body="Thank you for your purchase order. We have received it and will process it shortly.",
        #     pdf_path=None,
        # )

        processed += 1 # count of processed emails
        print(f"[WORKFLOW] ✓ Marked email {mark_result['id']} as read (processed={processed})")

    print("[WORKFLOW] ✓ All unread messages processed")


if __name__ == "__main__":
    # For development: process inbox until no unread messages remain
    asyncio.run(run_till_mail_read())
    
    # For UI inspection: uncomment this instead
    # serve([workflow], auto_open=True)
