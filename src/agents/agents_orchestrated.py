"""
Multi-Agent Orchestrator for O2C Purchase Order Processing

Architecture:
    Orchestrator Agent
        ├─> Email Triage Agent (decide PO vs non-PO)
        ├─> PO Parser Agent (emit PurchaseOrder JSON)
        └─> SKU Resolver Agent (choose best catalog SKU from candidates)
    
    Orchestrator-owned deterministic services:
        • Gmail fetch + reply
        • SKU candidate preparation (vector + CRM lookups)
        • Credit evaluation and totals computation
        • Invoice PDF rendering
        • Slack alerting and Airtable persistence

Flow:
    1. Orchestrator fetches unread emails via gmail_grabber()
    2. Triage Agent returns TriageResult; skip non-PO messages
    3. Parser Agent returns PurchaseOrder JSON
    4. Orchestrator prepares SKU candidates and calls SKU Resolver Agent
    5. Deterministic helpers handle credit, totals, comms, and CRM write
"""

import os
from pathlib import Path
from dotenv import load_dotenv  # Loads .env so env vars are available at runtime
from azure.identity import DefaultAzureCredential  # Default auth chain for Azure resources
from azure.ai.agents import AgentsClient  # Azure AI Foundry agent runtime client
from azure.ai.agents.models import (
    FunctionTool,
    ToolSet,
    ResponseFormatJsonSchema,
    ResponseFormatJsonSchemaType,
    ConnectedAgentTool,
)

# Import all Pydantic schemas
from src.shared.schemas_pydantic import TriageResult, PurchaseOrder, EnrichedPurchaseOrder
from src.email.gmail_grabber import authenticate_gmail, fetch_unread_emails
from src.crm import airtable_reader, airtable_writer  # Airtable adapters (currently placeholders)
from src.invoice.invoice_pdf_writer import create_invoice_pdf  # Invoice PDF helper (placeholder)
from src import ai_search_indexer  # Vector-search candidate builder scaffolding

# Load environment variables
load_dotenv()  # Ensure AZURE_* secrets are present before initializing clients
project_endpoint = os.getenv("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")  # Required endpoint for AgentsClient
model_deployment = os.getenv("AZURE_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")  # Default model used across agents

# Load agent prompts from markdown files
PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"  # ./src/agents/prompts

def load_prompt(filename: str) -> str:
    """Load agent instructions from markdown file."""
    prompt_path = PROMPTS_DIR / filename  # e.g. prompts/email_triage_agent.md
    return prompt_path.read_text(encoding="utf-8")  # Return full prompt text

# Initialize Azure AI Agents client
agent_client = AgentsClient(
    endpoint=project_endpoint,  # Azure AI Foundry project endpoint
    credential=DefaultAzureCredential()  # Uses managed identity / env credentials automatically
)


# ============================================================================
# TOOL DEFINITIONS - Functions that agents can DECIDE to call
# ============================================================================

def gmail_grabber():
    """
    Fetch unread Gmail messages and return structured email details.
    Returns list of dicts with id, sender, subject, snippet, body.
    """
    service = authenticate_gmail()  # Reuse cached Gmail credentials if available
    return fetch_unread_emails(service)  # List[Dict[str, str]]


# ============================================================================
# DETERMINISTIC SERVICES - Direct function calls (no agent decision needed)
# ============================================================================

def check_credit(customer_name: str, order_total: float) -> dict:
    """
    Check customer credit limit vs open AR in Airtable.
    Returns dict with approved: bool, credit_limit, open_ar, reason.
    """
    return airtable_reader.get_customer_credit(customer_name=customer_name, order_total=order_total)  # Gateway to CRM


def calculate_totals(order_lines: list) -> dict:
    """
    Calculate net amount, tax, shipping, grand total.
    Takes enriched order lines, returns totals dict.
    """
    pass  # TODO: implement deterministic pricing math once tax/shipping rules are finalized


def compose_confirmation_email(enriched_po: dict, totals: dict, credit_result: dict) -> str:
    """
    Compose email body for buyer confirmation (no subject needed since it's a reply).
    Uses simple template with order details, totals, and any holds/notes.
    """
    pass  # TODO: render email body (HTML or plain text) with friendly tone + credit/hold notes


def generate_invoice_pdf(enriched_po: dict, totals: dict) -> str:
    """
    Generate PDF invoice from HTML template.
    Returns URL/path to generated PDF for email attachment.
    """
    return create_invoice_pdf(enriched_po, totals)  # Delegates to invoice module (NotImplemented placeholder)


def send_email_reply(thread_id: str, body: str, attachment_url: str = None):
    """
    This function only sends the email reply to original Gmail thread,
    with the invoice PDF attachment from generate_invoice_pdf.
    The body string is taken from compose_confirmation_email().
    Uses Gmail API to reply in-thread with proper message references.
    Returns something like { "status": "sent", "message_id": ... }
    """
    pass  # TODO: implement Gmail reply leveraging thread_id + optional attachment MIME structure


def send_slack_notification(enriched_po: dict, credit_result: dict, needs_review: bool):
    """
    Post formatted message to Slack channel via incoming webhook.
    Return a small confirmation like { "status": "posted" }
    Always sent for every order. Uses Block Kit format with order summary.
    """
    pass  # TODO: format Slack payload (blocks) and POST via webhook URL


def add_order_to_crm(enriched_po: dict, totals: dict, invoice_pdf_url: str = None):
    """
    Add processed order to Airtable CRM:
    - Orders table, order_lines table, customer table (if new)
    - Reduce stock levels, update customer credit
    - Optionally add invoice PDF URL and review notes

    Calls into Airtable using the src/crm/airtable_writer.py helper;
    insert/update the relevant records, adjust inventory,
    and return data the agent can log ({ "order_id": ..., "status": "ok" })
    """
    return airtable_writer.record_order(enriched_po, totals, invoice_pdf_url=invoice_pdf_url)  # Persist order + inventory


def prepare_sku_candidates(payload: dict, top_k: int = 5) -> dict:
    """
    Build SKU candidate lists for the parsed purchase order.
    Expected payload shape: {"purchase_order": PurchaseOrder JSON}.
    Returns {"purchase_order": ..., "line_candidates": [...] } for SKU agent review.
    """
    return ai_search_indexer.build_candidates(payload=payload, limit=top_k)  # Delegates to vector-search scaffolding


# ============================================================================
# AGENT DEFINITIONS - Create specialized agents
# ============================================================================

with agent_client:  # Ensure client resources are cleaned up when block exits
    
    # ------------------------------------------------------------------------
    # 1. EMAIL TRIAGE AGENT
    # Role: Classify if email is a purchase order or not
    # Input: Single email JSON {id, sender, subject, body}
    # Output: TriageResult schema (is_po, confidence, reason)
    # ------------------------------------------------------------------------
    
    triage_response_format = ResponseFormatJsonSchemaType(  # Force JSON schema adherence for triage output
        json_schema=ResponseFormatJsonSchema(
            name="TriageResult",
            description="Classification result for a single email",
            schema=TriageResult.model_json_schema(),
        )
    )
    
    email_triage_agent = agent_client.create_agent(
        model=model_deployment,
        name="email-triage-agent",
        instructions=load_prompt("email_triage_agent.md"),
        response_format=triage_response_format,  # Agent must emit TriageResult schema
    )
    
    # ------------------------------------------------------------------------
    # 2. PO PARSER AGENT
    # Role: Extract structured purchase order data from email
    # Input: Email JSON that has been classified as a PO
    # Output: PurchaseOrder schema (po_number, customer, order_lines, etc.)
    # ------------------------------------------------------------------------
    
    po_parser_response_format = ResponseFormatJsonSchemaType(  # Structured PurchaseOrder schema
        json_schema=ResponseFormatJsonSchema(
            name="PurchaseOrderExtraction",
            description="Structured purchase order data extracted from email",
            schema=PurchaseOrder.model_json_schema(ref_template="#/components/schemas/{model}"),
        )
    )
    
    po_parser_agent = agent_client.create_agent(
        model=model_deployment,
        name="po-parser-agent",
        instructions=load_prompt("po_parser_agent.md"),
        response_format=po_parser_response_format,  # Enforce PurchaseOrder contract
    )
    
    # ------------------------------------------------------------------------
    # 3. SKU RESOLVER AGENT
    # Role: Pick the best SKU from orchestrator-provided candidates
    # Input: PurchaseOrder plus candidate list
    # Output: EnrichedPurchaseOrder schema with matched SKUs, prices, UOMs
    # ------------------------------------------------------------------------

    sku_resolver_response_format = ResponseFormatJsonSchemaType(  # Enforce EnrichedPurchaseOrder schema
        json_schema=ResponseFormatJsonSchema(
            name="EnrichedPurchaseOrder",
            description="Purchase order with matched SKUs and pricing",
            schema=EnrichedPurchaseOrder.model_json_schema(),
        )
    )
    
    sku_resolver_agent = agent_client.create_agent(
        model=model_deployment,
        name="sku-resolver-agent",
        instructions=load_prompt("sku_resolver_agent.md"),
        response_format=sku_resolver_response_format,  # Output must include matching_summary metadata
    )
    
    # ------------------------------------------------------------------------
    # ORCHESTRATOR AGENT
    # Role: Main coordinator that manages the entire workflow
    # Input: User request to process emails
    # Output: Summary of processed emails and actions taken
    # Tools: gmail_grabber + handoffs to 3 sub-agents + deterministic services
    # ------------------------------------------------------------------------
    
    # Create connected agent tools for handoffs
    triage_tool = ConnectedAgentTool(
        id=email_triage_agent.id,
        name="classify_email_as_po",
        description="Given raw email JSON (id, sender, subject, body), return TriageResult with is_po + reasoning."
    )
    
    parser_tool = ConnectedAgentTool(
        id=po_parser_agent.id,
        name="parse_purchase_order",
        description="Convert PO email JSON into PurchaseOrder schema with customer info and order_lines."
    )
    
    resolver_tool = ConnectedAgentTool(
        id=sku_resolver_agent.id,
        name="resolve_product_skus",
        description="Review provided candidate bundles, choose best SKU per line, and return EnrichedPurchaseOrder."
    )
    
    # Build orchestrator toolset with agent handoffs + deterministic services
    orchestrator_tools = FunctionTool({
        gmail_grabber,  # Fetch unread inbox items
        prepare_sku_candidates,  # Build vector-search candidate bundles
        check_credit,  # CRM credit exposure lookup
        calculate_totals,  # Deterministic totals computation
        compose_confirmation_email,  # Draft customer-facing body text
        generate_invoice_pdf,  # Produce invoice artifact
        send_email_reply,  # Reply on Gmail thread
        send_slack_notification,  # Notify internal team of outcome
        add_order_to_crm  # Persist order + inventory adjustments
    })
    orchestrator_toolset = ToolSet()  # Aggregate deterministic functions + agent handoffs
    orchestrator_toolset.add(orchestrator_tools)
    orchestrator_toolset.add(triage_tool)
    orchestrator_toolset.add(parser_tool)
    orchestrator_toolset.add(resolver_tool)
    
    # Enable auto function calling for orchestrator
    agent_client.enable_auto_function_calls(orchestrator_toolset)  # Allow orchestrator to auto-invoke approved tools
    
    orchestrator_agent = agent_client.create_agent(
        model=model_deployment,
        name="o2c-orchestrator-agent",
        instructions=load_prompt("orchestrator_agent.md"),
        toolset=orchestrator_toolset,  # Lets orchestrator auto-call both connected agents and local helpers
    )
    
    # ------------------------------------------------------------------------
    # EXECUTE WORKFLOW
    # ------------------------------------------------------------------------
    
    print("=" * 70)  # Banner divider for CLI trace
    print("O2C MULTI-AGENT ORCHESTRATOR - Purchase Order Processing")  # High-level heading
    print("=" * 70)
    print()
    
    # Create a new conversation thread
    thread = agent_client.threads.create()  # Fresh conversation thread scoped to this run
    print(f"[OK] Thread created: {thread.id}")
    
    # Send initial request to orchestrator
    agent_client.messages.create(  # Seed initial user request for orchestrator agent
        thread_id=thread.id,
        role="user",
        content="""Process all unread emails in the Gmail inbox.

For each email:
1. Classify if it's a purchase order
2. If yes, extract structured PO data
3. Build SKU candidate lists and resolve matches
4. Check credit, calculate totals, generate invoice PDF
5. Send confirmation email with PDF attachment
6. Send Slack notification with order summary
7. Add order to Airtable CRM

Provide a detailed summary of all actions taken.
"""
    )
    print("[OK] User request sent to orchestrator")
    print()
    
    # Run the orchestrator agent
    print("Running orchestrator agent workflow...")  # Kick off orchestrator run
    print("-" * 70)
    run = agent_client.runs.create_and_process(
        thread_id=thread.id,
        agent_id=orchestrator_agent.id,
        toolset=orchestrator_toolset,  # Allow LLM to access deterministic + connected tools
    )
    print("-" * 70)
    print(f"[OK] Run completed with status: {run.status}")  # Show final run status (succeeded, failed, etc.)
    print()
    
    # Retrieve and display all messages
    messages = agent_client.messages.list(thread_id=thread.id)  # Historical transcript for debugging/telemetry
    
    print("=" * 70)
    print("CONVERSATION TRANSCRIPT")
    print("=" * 70)
    print()
    
    for message in reversed(list(messages)):  # Print conversation newest-last for readability
        role = message.role.upper()  # USER / ASSISTANT / TOOL
        print(f"{role}:")
        print("-" * 70)
        
        for content_block in message.content:  # Iterate through message parts (text/attachments)
            if hasattr(content_block, 'text'):
                print(content_block.text.value)  # Plain text payload
            else:
                print(content_block)  # Fallback for non-text payloads
        
        print()
    
    print("=" * 70)
    print("WORKFLOW COMPLETE")
    print("=" * 70)
