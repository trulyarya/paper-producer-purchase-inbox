# PaperCo O2C Email Intake Demo

AI-driven Order-to-Cash assistant that turns purchase order emails into ready-to-fulfill orders, invoices, and customer updates across Gmail, Airtable, Azure AI, and Slack.

> [!IMPORTANT]
> This app is still under construction and may not work yet. Updates are being made regularly. A dedicated and detailed Youtube video walkthrough is planned. The thumbnail below refers to it as it's being produced:

![Ari-O2C-Mail-Agents-Screenshot](./docs/thumbnail_video.png)

## Why This Matters (O2C)

- Reduce cycle time: move from email to invoice in minutes, not days.
- Improve accuracy: structured extraction + validation reduces manual errors and revenue leakage.
- Increase cash velocity: faster confirmations and invoicing help lower DSO and speed collections.
- Scale operations: agents handle variability in real emails without brittle rules.
- Better customer experience: timely confirmations and clear rejections keep buyers informed.

### Beginner Corner (Quick Glossary)

- Purchase Order (PO): a buyer’s request that authorizes a purchase.
- O2C (Order‑to‑Cash): steps from receiving an order to collecting payment.
- SKU: stock keeping unit; a product identifier used for pricing and inventory.
- DSO: days sales outstanding; lower is better for cash flow.

## Delivery Status

- ✅ Azure infrastructure (Bicep + deploy script)
- ✅ Gmail + Slack integrations
- ✅ Airtable base with sample catalog & customers
- ✅ Multi-agent workflow with conditional routing
- ✅ Azure AI Search index population & invoice PDF generation
- 🚧 CRM record sync, container deployment, scheduled polling, REST wrapper, E2E tests

## How It Works

1. **Listen** – `run_till_mail_read()` loops over unread Gmail messages and spins up a fresh workflow per email (see `workflow.md` for the visual map).
2. **Reason** – Specialized agents classify, parse, resolve SKUs, check credit, decide, and route the order down fulfill or reject paths.
3. **Act** – Deterministic tools update inventory/credit, generate invoices, send confirmation or rejection emails, and alert the ops Slack channel for fulfilled orders.

### Agents at a Glance

| Agent | Role | Output | Core tools |
|---|---|---|---|
| classifier | Picks the next unread Gmail message and flags if it is a PO | `ClassifiedEmail` | `emailing.gmail_tools.fetch_unread_emails()` |
| parser | Structures the email into customer + line items | `ParsedPO` | (tool slot reserved for text cleanup) |
| resolver | Matches SKUs, prices items, checks credit, computes totals | `ResolvedPO` | `agents.resolver.check_credit()` |
| decider | Evaluates fulfillability | `Decision` | – |
| fulfiller | Executes the happy path: inventory, CRM stub, invoice, Slack | `FulfillmentResult` | `update_inventory`, `update_customer_credit`, `add_order_to_crm`, `generate_invoice`, `send_slack_notification` |
| rejector | Handles unfulfillable orders with messaging | `RejectResult` | – |

### Workflow Details

- The classifier preserves the original Gmail `id`; downstream agents reuse it for replies and mark-as-read.
- Parser keeps business logic light—resolver adds pricing, availability, and credit information, with computed totals on the Pydantic model.
- Decider uses the resolver payload only; no external tool calls.
- Fulfiller uses Slack and invoice helpers; rejector uses only email reply (no Slack). Add the Gmail reply helpers as workflow tools when ready.

### Overall Dataflow

```txt
                              +----------------------+
                              |      Gmail Inbox     |
                              +----------+-----------+
                                         |
                                         v
                           +-------------------------+
                           |       classifier        |
                           +-----------+-------------+
                                       |
                                       v
                           +-------------------------+
                           |         parser          |
                           +-----------+-------------+
                                       |
                                       v
                           +-------------------------+
                           |         resolver        |
                           +-----+-------------+-----+
                                 |             |
                                 |             v
                                 |    +--------------------+
                                 |    | Azure AI Search    |
                                 |    |  (SKU matching)    |
                                 |    +--------------------+
                                 v
                        +---------------------+
                        |     Airtable CRM    |
                        | (catalog + customers)|
                        +----------+----------+
                                   |
                                   v
                           +-------------------------+
                           |         decider         |
                           +-----+-------------+-----+
                                 |             |
                         FULFILLABLE      UNFULFILLABLE
                                 |             |
                                 v             v
                      +----------------+   +----------------+
                      |    fulfiller   |   |    rejector    |
                      +--------+-------+   +--------+-------+
                               |                    |
                               |                    v
                               |          (no Slack notifications)
                               v
                  +-----------------------+     +----------------------+
                  | Azure Blob Storage    |     |        Slack         |
                  |   (invoice PDFs)      |     | (fulfilled orders)   |
                  +-----------+-----------+     +-----------+----------+
                              |
                              +-------------------------+
                                                        |
                                                        v
                              mark_email_as_read() → next email
```

### Third‑Party Integrations
- Gmail API: fetch unread mail, send replies, and mark-as-read via OAuth 2.0.
- Airtable: catalog + customer data and simple CRM persistence.
- Azure AI Search: semantic/vector search to match line items to SKUs.
- Azure OpenAI: reasoning for agent prompts (classification, parsing, decisions).
- Azure Blob Storage: durable storage for generated invoice PDFs.
- Slack Webhooks: operations notifications (fulfilled orders only).

## Setup Guide

### 1. Deploy Azure foundation
```bash
open infra/main.bicepparam   # adjust names, regions, secrets
cd infra && ./deploy.sh
```

### 2. Connect supporting services

Create a `.env` with the minimum required variables:

```env
# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ

# Airtable
AIRTABLE_API_KEY=pat_xxx
AIRTABLE_BASE_ID=app_xxx
AIRTABLE_PRODUCTS_TABLE=Products
AIRTABLE_CUSTOMERS_TABLE=Customers

# Azure AI
AZURE_OPENAI_ENDPOINT=https://YOUR-openai.openai.azure.com
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large
AZURE_SEARCH_SERVICE_ENDPOINT=https://YOUR-search.search.windows.net
```

- Slack: enable Incoming Webhooks on your workspace app and paste the URL above.
- Airtable: create base “PaperCo-CRM” and import CSVs from `data/sample/` (Products → Customers → Orders → Order-Lines → Invoices). Set field types and link tables as described. Create a Personal Access Token with `data.records:read` and `data.records:write` and copy your Base ID.
- Gmail: in Google Cloud, enable the Gmail API, set up the OAuth consent screen (Testing, add your account), create OAuth “Desktop app” credentials and download as `cred/credentials.json`. Run the quickstart to create `cred/token.json`. Scopes: `gmail.readonly`, `gmail.modify`, `gmail.send`.

### 3. Populate Azure AI Search```bash

```bash
python -m src.ai-search.azure_search_tools <<'PY'
from azure_search_tools import (
    create_products_index_schema,
    create_customer_index_schema,
    ingest_products_from_airtable,
    ingest_customers_from_airtable,
)
create_products_index_schema()
create_customer_index_schema()
ingest_products_from_airtable()
ingest_customers_from_airtable()
PY
```

### 4. Run the workflow

```bash
python -m src.workflow.workflow
```
The loop processes each unread purchase-order email, completes the agent workflow, and calls `mark_email_as_read()` when finished.

## Project Structure

```txt
paper-producer-purchase-inbox/
├── infra/                 # Bicep templates, params, deploy script
├── src/
│   ├── agents/            # Agent definitions & shared tooling
│   ├── emailing/          # Gmail auth + helpers
│   ├── ai-search/         # Azure AI Search schema + ingestion
│   └── workflow/          # Workflow builder entrypoints
├── data/sample/           # Airtable seed CSVs
├── tests/                 # (planned) automated coverage
└── workflow.md            # Color ASCII workflow map & notes
```

## Key Files

- `src/workflow/workflow.py` – builds the agent DAG and runs the Gmail polling loop.
- `workflow.md` – color-coded ASCII map of the workflow plus stage cheatsheet.
- `src/agents/` – classifier, parser, resolver, decider, fulfiller, rejector definitions.
- `src/emailing/gmail_tools.py` – Gmail auth, fetch, reply, and label helpers.
- `src/ai-search/azure_search_tools.py` – index schemas and Airtable ingestion.
- `infra/` – Bicep templates, parameters, and deployment script.

## Tech Stack

- Python 3.12+, custom async workflow builder, Pydantic models
- Azure OpenAI + Azure AI Search + Azure Blob Storage
- Airtable (catalog & CRM data), Gmail API (OAuth 2.0), Slack webhooks
- Azure Bicep for IaC, Azure Container Apps planned for hosting

## Integrations & Costs

- Gmail API for intake and replies, Slack webhooks for ops notifications (fulfilled orders only), Airtable as the lightweight CRM, Azure AI Search for vector SKU resolution, Azure Blob Storage for invoice PDFs.
- Expect roughly \$115–\$170/month at light load (Search + OpenAI dominate the spend).

## Next Up

- Sync fulfilled orders back into the CRM
- Ship containerized deployment + scheduled polling job
- Wrap agents with FastAPI and expand automated tests

## License

MIT License
