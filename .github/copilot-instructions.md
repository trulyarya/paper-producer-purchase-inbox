# PaperCo O2C Email Intake - AI Agent Instructions

## Project Overview

This is an **Order-to-Cash (O2C) workflow automation** that processes purchase order emails through a multi-agent pipeline. It classifies emails, parses customer data, resolves SKUs via semantic search, validates credit/inventory, and either fulfills orders (generates invoices, sends confirmations, alerts Slack) or rejects them with explanations.

**Core Architecture:** Agent-based workflow using Azure AI Foundry's `agent-framework` with conditional routing, Azure AI Search for semantic SKU/customer matching, Airtable as lightweight CRM, and Gmail API for email intake/replies.

## Key Technical Patterns

### Agent Structure & Workflow Builder

Agents are defined using `ChatAgent` from `agent-framework` with structured I/O via Pydantic models:

```python
from agent_framework import ChatAgent, ai_function
from agents.base import chat_client  # Shared Azure OpenAI client

agent = ChatAgent(
    chat_client=chat_client,
    name="agent_name",
    instructions="Clear prompt...",
    tools=[tool_func1, tool_func2],
    response_format=OutputSchema,  # Pydantic BaseModel
)
```

**Workflow construction** (`src/workflow/workflow.py`):
- Use `WorkflowBuilder` to chain agents with conditional edges
- Routing functions (`should_parse`, `should_fulfill`, etc.) inspect `resp.agent_run_response.value`
- Each email spawns a fresh workflow via `create_workflow()`
- Always preserve Gmail `message_id` through the pipeline for replies and idempotency
- **Human-in-the-loop approval:** Implemented in the `send_confirmation_email_with_approval` tool. The tool posts to Slack and BLOCKS execution until a human replies 'approve' or 'deny'. If approved, it immediately sends the confirmation email. If denied, it returns without sending. This ensures the email can only be sent after human approval.

### Tools: @ai_function Decorator

Expose functions to agents using `@ai_function` from `agent-framework`:

```python
from agent_framework import ai_function

@ai_function
def my_tool(param: str) -> dict:
    """Clear docstring explaining what the tool does - agents see this."""
    return {"result": "value"}
```

Tools must have descriptive docstrings—agents use them to decide when to call. Avoid adding tools that make state-changing calls to decision agents (like `decider`).

**Human approval for tools (blocking pattern):**
```python
from agent_framework import ai_function

@ai_function
def send_confirmation_email_with_approval(message_id: str, invoice_url: str, retrieved_po: dict) -> dict:
    """Post order to Slack, BLOCK until human approves/denies, send email if approved."""
    # 1. Post to Slack
    thread_ts = post_approval_request(retrieved_po)
    
    # 2. Block and poll for human reply in thread (with timeout)
    approved = get_approval_from_slack(channel, thread_ts, timeout=300)
    
    # 3. If approved, send email immediately
    if approved:
        respond_confirmation_email(message_id, invoice_url, retrieved_po)
        return {"status": "approved", "email_sent": "true"}
    else:
        return {"status": "denied", "email_sent": "false"}
```

**Why not use `@ai_function(approval_mode="always_require")`?**
- The agent framework's approval mode works at the **agent.run()** level (single agent)
- **Workflows** (`WorkflowBuilder`) don't expose `user_input_requests` in `WorkflowRunResult`
- Approval must be handled inside the tool itself (blocking pattern)

**Important:** When the agent calls `send_confirmation_email_with_approval()`, execution pauses until a human replies in Slack. The tool handles both approval AND email sending atomically - the email can only be sent after approval.

### Schema Design with Pydantic

- All agent inputs/outputs are Pydantic `BaseModel` subclasses with `ConfigDict(extra="forbid")`
- Use `Annotated[type, Field(description="...")]` for every field—descriptions guide agent reasoning
- Leverage `@computed_field` for derived values like totals, subtotals, and flags (see `RetrievedPO`, `RetrievedItem`)
- Nested schemas flow through agents: `Email` → `ClassifiedEmail` → `ParsedPO` → `RetrievedPO` → `Decision`

### Data Flow & Agent Responsibilities

1. **classifier** → Fetches unread Gmail, flags PO emails (`ClassifiedEmail`)
2. **parser** → Extracts customer + line items (`ParsedPO`)
3. **retriever** → Semantic search for customers/SKUs, enriches with pricing/credit/inventory (`RetrievedPO` with computed fields)
4. **decider** → LLM-only evaluation of fulfillability (`Decision`)
5. **fulfiller** → Updates Airtable (inventory, credit), syncs to Azure AI Search, generates invoice PDF, sends confirmation email, posts to Slack (`FulfillmentResult`)
6. **rejector** → Sends rejection email with reason (`RejectResult`)

**Invariant:** Downstream agents receive the previous agent's output schema as input. The `retriever` computes all totals once; `decider` and `fulfiller` never recalculate.

### Azure AI Search Integration

**Setup sequence** (run before first workflow execution):
```python
from aisearch.azure_search_tools import (
    create_products_index_schema,
    create_customer_index_schema,
    ingest_products_from_airtable,
    ingest_customers_from_airtable,
)
# Create schemas, then ingest data
```

**Search usage in retriever:**
```python
search_products(query="recycled cardboard")  # Hybrid search with embeddings
search_customers(query="GreenOffice GmbH")   # Matches customers by name/email
```

Fulfiller re-syncs after inventory/credit changes: `ingest_products_from_airtable()` and `ingest_customers_from_airtable()`.

### Gmail Integration Patterns

- **Authentication:** OAuth2 tokens stored in `cred/token.json`, credentials in `cred/credentials.json`
- **Fetching:** `fetch_unread_emails()` returns list of `{id, subject, sender, body, snippet}` dicts
- **Replies:** Use `respond_confirmation_email(message_id, pdf_url)` or `respond_unfulfillable_email(message_id, reason)` to maintain thread context
- **Mark as read:** Always call `mark_email_as_read(message_id)` after workflow completes to avoid reprocessing

### Environment & Configuration

`.env` variables (see `README.md` setup):
- **Azure:** `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`, `AZURE_SEARCH_ENDPOINT`
- **Airtable:** `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, table names
- **Slack:** `SLACK_WEBHOOK_URL`
- **Gmail:** OAuth credentials in `cred/` directory

Shared Azure client (`src/agents/base.py`): Uses `DefaultAzureCredential` (managed identity) with fallback to `AzureCliCredential`.

### Path Resolution for Container Compatibility

When referencing static files (templates, credentials), resolve paths relative to the module:

```python
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[2]  # Project root
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "invoice" / "invoice_template.html"
```

This ensures code works regardless of current working directory (dev vs. containerized).

## Development Workflows

### Running the Pipeline

```bash
python -m src.workflow.workflow  # Polls Gmail until no unread PO emails
```

### Indexing Airtable Data

```bash
python -c "
from src.aisearch.azure_search_tools import *
create_products_index_schema()
create_customer_index_schema()
ingest_products_from_airtable()
ingest_customers_from_airtable()
"
```

### Infrastructure Deployment

```bash
cd infra
# Edit main.bicepparam first with your Azure config
./deploy.sh  # Creates resource group and deploys Bicep templates
```

## Common Pitfalls

1. **Breaking the Gmail ID chain:** The `message_id` from classifier must propagate through all agents for replies to thread correctly
2. **Forgetting to sync search indexes:** After updating Airtable inventory/credit, always call `ingest_products_from_airtable()` and `ingest_customers_from_airtable()`
3. **Recalculating totals in downstream agents:** All financial computations happen in `retriever` via `@computed_field`—later agents consume these values
4. **Adding tools to decider:** The decider is LLM-only evaluation logic; avoid giving it side-effect tools
5. **Mixing up table names:** Airtable table names are configurable via env vars, not hardcoded

## Codebase Navigation

- **`src/agents/`** – All agent definitions (classifier, parser, retriever, decider, fulfiller, rejector)
- **`src/workflow/workflow.py`** – Workflow construction and Gmail polling loop
- **`src/aisearch/azure_search_tools.py`** – Index schemas, ingestion, search functions
- **`src/crm/airtable_tools.py`** – Airtable CRUD operations (inventory, customers, credit)
- **`src/emailing/gmail_tools.py`** – OAuth, fetch, reply, mark-as-read functions
- **`src/invoice/invoice_tools.py`** – HTML → PDF invoice generation with Jinja2/WeasyPrint
- **`src/messaging/slack_msg_sender.py`** – Slack webhook notifications
- **`workflow.md`** – Visual ASCII workflow map with agent stage cheatsheet
- **`docs/PRD.md`** – Product requirements, architecture diagram, success metrics
- **`infra/`** – Bicep IaC templates and deployment scripts

## Testing Strategy

- **Manual testing:** Send PO emails to Gmail, observe logs and Slack/Gmail outputs
- **Unit tests:** Planned in `tests/` directory (not yet implemented)
- **Integration tests:** Validate full workflow from inbox to invoice/rejection

When modifying agents, verify schema compatibility by checking input/output types match workflow edges.


## Notes

- Do NOT use emojis anywhere in the code, prompts, comments, documentation, or instructions!
- All refactoring or code generation must be concise, clear, and maintainable, without unnecessary complexity
- Follow established coding conventions and best practices for the language and framework in use, without adding dependencies.
- Focus on beginner-friendly code and explanations and write clearly, and informatively, but NOT too verbose!
- Do NOT try to capture every edge case; prioritize the core happy path and common scenarios. Do NOT catch every possible exception!
- Always add comments and docstrings, especially when creating or modifying functions, classes, or complex logic, but avoid over-commenting simple code!
- Less is more: prioritize brevity, "DRY", simplicity and clarity in code and explanations, without adding a lot of extra details or new lines of code!