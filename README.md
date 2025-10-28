# PaperCo O2C Email Intake Demo

AI-powered Order-to-Cash system that converts purchase order emails into invoices using Azure AI agents.

## Current Status

- [x] Project planning and PRD
- [x] Azure infrastructure (Bicep)
- [x] Slack Webhook integration
- [x] Airtable base schema and setup (sample data loaded)
- [x] Gmail integration and API setup
- [x] Multi-agent workflow with conditional routing
- [x] Email classification and PO parsing agents
- [x] SKU resolution with candidate preparation
- [x] Credit check and order validation
- [x] Order fulfillment and rejection flows
- [x] Email reply composition and sending
- [x] Slack notifications for operations team
- [x] Azure AI Search index population from Airtable
- [x] Invoice PDF generation (HTML template + blob storage)
- [ ] CRM order and invoice record creation
- [ ] Container App deployment (Docker)
- [ ] Scheduled job (check emails every 5 minutes)
- [ ] FastAPI REST API wrapper
- [ ] End-to-end testing and validation

## What This Does

1. Monitors Gmail inbox for purchase order emails
2. Uses a multi-agent workflow with specialized agents and conditional routing:
   - **Classifier** – identifies purchase orders from inbox messages
   - **Parser** – extracts structured PO data (customer, line items, quantities)
   - **Resolver** – matches items to SKUs, checks credit, calculates totals
   - **Decider** – determines if order is fulfillable (availability + credit)
   - **Fulfiller** – processes approved orders (inventory, CRM, invoice, notifications)
   - **Rejector** – handles unfulfillable orders with customer communication
3. Integrates deterministic tools for credit checks, inventory updates, invoice generation, and CRM persistence
4. Sends confirmation emails to customers and Slack notifications to operations team

### Multi-Agent Workflow

The system uses six specialized agents with conditional routing:

#### 1. Classifier Agent

**Purpose**: Fetches unread Gmail messages and identifies purchase orders.

**Output**: `ClassifiedEmail` with `is_po` boolean, confidence reason, and the email object.

**Why an agent**: Handles variability in email formats, subjects, and sender patterns that regex cannot reliably detect.

#### 2. Parser Agent

**Purpose**: Extracts structured purchase order data from confirmed PO emails.

**Output**: `ParsedPO` with customer details and line items (SKU/name, quantity).

**Why an agent**: Interprets natural language requests, handles typos and formatting inconsistencies, and normalizes data into a clean structure.

#### 3. Resolver Agent

**Purpose**: Resolves products, checks customer credit, and calculates order totals.

**Output**: `ResolvedPO` with matched SKUs, pricing, availability, credit status, and calculated tax/shipping.

**Tools**: `calculate_totals`, `check_credit`, `prepare_sku_candidates` (planned for AI Search integration).

#### 4. Decider Agent

**Purpose**: Evaluates if the order can be fulfilled based on item availability and customer credit.

**Output**: `Decision` with status (`FULFILLABLE` or `UNFULFILLABLE`) and reasoning.

**Logic**: No tools needed—analyzes the `ResolvedPO` data directly.

#### 5. Fulfiller Agent (Conditional)

**Purpose**: Processes approved orders end-to-end.

**Actions**: Updates inventory, adjusts customer credit, generates invoice PDF, creates CRM records, sends confirmation email, notifies Slack.

**Output**: `FulfillmentResult` with order ID and invoice number.

**Route condition**: Triggered only when `status == "FULFILLABLE"`.

#### 6. Rejector Agent (Conditional)

**Purpose**: Handles unfulfillable orders with professional customer communication.

**Actions**: Composes rejection email explaining issues (credit/availability), sends reply, optionally notifies operations team.

**Output**: `RejectResult` confirming successful rejection handling.

**Route condition**: Triggered only when `status == "UNFULFILLABLE"`.

## Quick Start

### Step 1: Deploy Azure Infrastructure

```bash
# 1. Edit configuration
open infra/main.bicepparam

# 2. Deploy to Azure
cd infra
./deploy.sh
```

### Step 2: Set Up Data Sources and Third-Party Integrations

#### 1. Slack Integration

##### Create a Slack App

- Go to <https://slack.com> and create a new free (personal) workspace if you don't have one
- Go to <https://api.slack.com/apps>
- Click "Create New App" and choose "From scratch"
- Name your app and select your workspace

##### Enable Incoming Webhooks

Since this is a simple notification use case, we will use Incoming Webhooks:

- Go to "Incoming Webhooks" on the left side-bar in your app settings and enable it
- Copy the Webhook URL

##### Set Up Environment Variables

- Add it to Webhook URL to `.env` file as `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL`

##### Install Dependencies (Optional)

Since we only want to send Block-Kit webhook notifications, we could simply do it using the `requests` library in Python (as a simple API POST request). Using the Slack SDK is also an option:

- Add `slack-sdk` to your `requirements.txt` if you choose to use it.
- Import and initialize the Slack client with your token.
- Send a `blocks` payload to the webhook URL using Block Kit:

```python
from slack_sdk import WebClient

webhook = WebClient(os.getenv("SLACK_WEBHOOK_URL"))
response = webhook.send(
    text="fallback",
    blocks=[
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "You have a new request:\n*<fakeLink.toEmployeeProfile.com|Fred Enriquez - New device request>*"
            }
        }
    ]
)
```

#### 2. Airtable Setup (Tables: products, customers, inventory, orders, invoices)

Spin up a writable “fake CRM” in Airtable using the CSVs already in your repo at `data/sample/`.

##### Create the base and import

1. On <https://airtable.com/>, create a new Base named “PaperCo-CRM”.

2. Import each CSV as a new table named below, in this order, and set the primary field exactly as shown:

- Products, `data/sample/airtable_products.csv`, primary `SKU`
- Customers, `data/sample/airtable_customers.csv`, primary `Customer ID`
- Orders, `data/sample/airtable_orders.csv`, primary `Order ID`
- Order-Lines, `data/sample/airtable_order_lines.csv`, primary `Line ID`
- Invoices, `data/sample/airtable_invoices.csv`, primary `Invoice ID`

##### Quick field types

After importing, quickly set types so the UI and API behave well.

- Products, set `Unit Price` to Currency, `Qty Available` to Number (integer), `Active` to Checkbox, `Last Updated` to Date time.
- Customers, set `Credit Limit` and `Open AR` to Currency, `Status` to Single select (Active, On Hold).
- Orders, set `Order Date` and `Requested Ship Date` to Date, `Status` to Single select (New, Priced, Invoiced, Sent), `Net Amount` to Currency.
- Order-Lines, set `Qty` to Number, `Unit Price` to Currency, `Line Total` to Currency, `Match Score` to Number with 3 decimals.
- Invoices, set `Amount Due` to Currency, `PDF URL` to URL, `Sent At` to Date time, `Status` to Single select (Draft, Sent).

##### Link the tables

Turn plain text IDs into Links so Airtable auto-joins records. Do this in the order below.

1. In **Orders**, change the `Customer` field type to “Link to another record”, pick **Customers**. Airtable will auto match by `Customer ID`.
2. In **Order-Lines**, change `Order` to a Link to **Orders**, and then, `Product` to a Link to **Products**. Airtable will auto match by `Order ID` and `SKU`.
3. In **Invoices**, change `Order` to a Link to **Orders**.
4. In **Orders**, also change `Invoice` to a Link to **Invoices**, or leave it as a plain text reference.

- Tip: links auto-populate only if the values match the target table’s primary field.

##### API access

- Create a Personal Access Token (somewhere in <https://airtable.com/create/tokens>) with scopes `data.records:read` and `data.records:write`, restrict to this Base.
- Note your Base ID and table names exactly as above and save them in `.env`.

You can now insert Orders and Order Lines, update Invoices with the PDF URL, and read Products for pricing and SKU matching.

#### 3. Google Cloud Setup (Gmail Integration)

##### Create a Google Cloud project

- Open <https://console.cloud.google.com/>, click the project picker, New Project, complete the form, Create.

##### Enable the Gmail API

- In the left menu, go to APIs and Services, Library, search “Gmail API”, open it, click Enable.

##### Configure the OAuth consent screen

- Go to APIs and Services, OAuth consent screen.
- User type, choose External.
- Fill App name, User support email, and Developer contact info, then Continue.
- Add yourself as a Test user, Audience, Add users, enter your Gmail address, Save.
- Leave the app in Testing for a personal demo. Testing mode allows up to 100 test users and shows the unverified app screen.

**Tip**: Just add the new Email address as a Test user, delete or rename your existing `token.json`(downloaded through the Quickstart app below), rerun the OAuth flow, and sign in as the new mailbox. Your app will now act on **that** mailbox.

##### Create OAuth 2.0 credentials

- Go to APIs and Services, Credentials, Create Credentials, OAuth client ID.
- Application type, choose Desktop app, then Create.
- Download the credentials file, this is your `client_secret.json`. You will use it to obtain a refresh token on your machine. **Keep it safe!**

##### Know the Gmail API scopes you will request in code

- Read only, `https://www.googleapis.com/auth/gmail.readonly`
- Read and mark as read, `https://www.googleapis.com/auth/gmail.modify`
- Send email, `https://www.googleapis.com/auth/gmail.send`

**Tip:** You do not have to preselect these on the consent screen for a test app, your code will request them and the consent screen will display them.

##### Quick check with Google’s Python quickstart (Optional)

- Follow the Quickstart (<https://developers.google.com/workspace/gmail/api/quickstart/python>) to run a small script once (saved in `scratch/gmail_quickstart.py`), it will open a browser, you sign in with your Gmail, and it writes `token.json`. Keep both files safe, `client_secret.json` and `token.json`.

You now have a project with Gmail API enabled, an OAuth consent screen in Testing with you as a test user, and a Desktop OAuth client you can use to obtain a refresh token for your app.

#### Azure AI Search vector index population from Airtable

1. DONE WITH BICEP: Set up Azure AI Search service
2. Create vector index for product catalog
3. Populate index with data from Airtable

#### Blob Storage container configuration

1. DONE WITH BICEP: Create Blob Storage container
2. Set up access policies and permissions

### Step 3: Build FastAPI Backend (Coming Next)

- Email processing pipeline
- AI agent implementations
- Deterministic services

## Project Structure

```txt
paper-producer-purchase-inbox/
├── infra/                    # Azure infrastructure (Bicep)
│   ├── main.bicep            # Infrastructure template
│   ├── main.bicepparam       # Configuration values
│   ├── deploy.sh             # Deployment script
│   └── README.md             # Deployment guide
├── src/                      # Python application code
├── tests/                    # Unit and integration tests
├── PRD.md                    # Product Requirements including Architecture
└── README.md                 # This file
```

## Documentation

- **[PRD.md](PRD.md)** - Product requirements and goals
- **[infra/README.md](infra/README.md)** - Beginner's guide to Bicep

## Architecture

```txt
Gmail → FastAPI → AI Agents → Services → Invoice PDF
                     ↓                      ↓
                 AI Search              Blob Storage
                 AI Foundry             Airtable (all data)
                                           ↓
                                    Slack Notification
```

**High-Level Snapshot:**

```txt
                     HIGH LEVEL SOLUTION ARCHITECTURE

   [Gmail Inbox]              [Airtable - All Business Data]                 [Slack]
         |                                   |                                  ^
         |                                   |                                  |
         v                                   |                                  |
+-----------------------------------------------------------------------------------------+
|                     Azure Container Apps - O2C App and API                              |
|                          (single entry point for the demo)                              |
+-----------------------------+-----------------------------+-----------------------------+
                              |                             |
                              v                             v
                  [Azure AI Foundry Agent Service]     [Azure Blob Storage]
                              |                            (invoice PDFs)
                              |
                              v
                +--------------------------+    +------------------------+
                |     Azure AI Foundry     |    |     Azure AI Search    |
                |  (reasoning, embeddings) |    |    (SKU vector index)  |
                +--------------------------+    +------------------------+
```

**Multi-Agent Workflow with Conditional Routing:**

```txt
        ┌──────────────┐
        │ CLASSIFIER   │  Fetches unread emails, identifies POs
        └──────┬───────┘
               │ if is_po == True
               ↓
        ┌──────────────┐
        │   PARSER     │  Extracts customer and line items
        └──────┬───────┘
               │
               ↓
        ┌──────────────┐
        │  RESOLVER    │  Matches SKUs, checks credit, calculates totals
        └──────┬───────┘
               │
               ↓
        ┌──────────────┐
        │   DECIDER    │  Evaluates fulfillability
        └──────┬───────┘
               │
        ┌──────┴───────────────┐
        │                      │
        ↓                      ↓
┌───────────────┐      ┌──────────────┐
│  FULFILLER    │      │  REJECTOR    │
│ (if FULFILL-  │      │ (if UNFULF-  │
│  ABLE)        │      │  ILLABLE)    │
└───────────────┘      └──────────────┘
│                      │
├─ Update inventory    ├─ Compose rejection email
├─ Update credit       ├─ Send email reply
├─ Generate invoice    └─ Notify Slack (optional)
├─ Create CRM records
├─ Send confirmation
└─ Notify Slack
```

**Tool Usage by Agent:**

```txt
Classifier
├─ gmail_grabber()            Fetch unread messages

Parser
├─ clean_email_payload()      Normalize email text

Resolver
├─ prepare_sku_candidates()   Build product match candidates (AI Search planned)
├─ calculate_totals()          Compute subtotal, tax, shipping, total
└─ check_credit()              Validate customer credit availability

Decider
└─ (no tools)                  Analyzes ResolvedPO data directly

Fulfiller
├─ update_inventory()          Deduct ordered quantities
├─ update_customer_credit()    Adjust credit exposure
├─ generate_invoice_pdf()      Create invoice document
├─ add_order_to_crm()          Persist order records
├─ compose_fulfillment_email() Draft confirmation message
├─ send_email_reply()          Send email with invoice attachment
└─ send_slack_notification()   Alert operations team

Rejector
├─ send_email_reply()          Send rejection explanation
└─ send_slack_notification()   Notify ops team (optional)
```

**Agent Data Flow:**

```txt
┌─────────────────────────────────────────────────────────────────────────┐
│                          GMAIL INBOX                                    │
│                    (Unread purchase order emails)                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   CLASSIFIER AGENT     │
                    │  Tool: gmail_grabber   │
                    └────────┬───────────────┘
                             │
                             ▼
              ClassifiedEmail {
                email: {id, subject, sender, body}
                is_po: bool
                reason: string
              }
                             │
                             │ Conditional: if is_po == True
                             ▼
                    ┌────────────────────────┐
                    │     PARSER AGENT       │
                    │ Tool: clean_email_*    │
                    └────────┬───────────────┘
                             │
                             ▼
              ParsedPO {
                email_id: string
                customer_name: string
                customer_address: string
                line_items: [{sku_or_name, qty}]
              }
                             │
                             ▼
                    ┌────────────────────────┐
                    │    RESOLVER AGENT      │
                    │ Tools: calculate_*,    │
                    │  check_credit, etc.    │
                    └────────┬───────────────┘
                             │
                             ▼
              ResolvedPO {
                email_id, customer_id, customer_name
                customer_credit_ok: bool
                items: [{sku, name, qty, price, available, subtotal}]
                tax: float
                shipping: float
                total: float
              }
                             │
                             ▼
                    ┌────────────────────────┐
                    │     DECIDER AGENT      │
                    │   (No tools needed)    │
                    └────────┬───────────────┘
                             │
                             ▼
              Decision {
                status: "FULFILLABLE" | "UNFULFILLABLE"
                reason: string
                payload: ResolvedPO
              }
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────────┐      ┌──────────────────────┐
    │  FULFILLER AGENT    │      │   REJECTOR AGENT     │
    │  (if FULFILLABLE)   │      │  (if UNFULFILLABLE)  │
    │                     │      │                      │
    │ Tools:              │      │ Tools:               │
    │ • update_inventory  │      │ • send_email_reply   │
    │ • update_credit     │      │ • send_slack_*       │
    │ • generate_invoice  │      │                      │
    │ • add_order_to_crm  │      └──────────┬───────────┘
    │ • compose_email     │                 │
    │ • send_reply        │                 ▼
    │ • send_slack_*      │        RejectResult {
    └──────────┬──────────┘          ok: bool
               │                   }
               ▼                        │
    FulfillmentResult {                 │
      ok: bool                          │
      order_id: string                  │
      invoice_no: string                │
    }                                   │
               │                        │
               └────────────┬───────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │     WORKFLOW COMPLETE       │
              │  • Email marked as read     │
              │  • Customer notified        │
              │  • Operations team alerted  │
              └─────────────────────────────┘
```

**Pydantic Schemas:**

```txt
Email                        ClassifiedEmail
├─ id                        ├─ email: Email
├─ subject                   ├─ is_po: bool
├─ sender                    └─ reason: str
└─ body

ParsedPO                     LineItem
├─ email_id                  ├─ sku_or_name: str
├─ customer_name             └─ qty: int (>0)
├─ customer_address
└─ line_items: List[LineItem]

ResolvedPO                   ResolvedItem
├─ email_id                  ├─ sku: str
├─ customer_id               ├─ name: str
├─ customer_name             ├─ qty: int (>0)
├─ customer_credit_ok: bool  ├─ price: float (>=0)
├─ items: List[ResolvedItem] ├─ available: bool
├─ tax: float                └─ subtotal: float
├─ shipping: float
└─ total: float

Decision                     FulfillmentResult
├─ status: FULFILLABLE       ├─ ok: bool
│   | UNFULFILLABLE          ├─ order_id: str
├─ reason: str               └─ invoice_no: str
└─ payload: ResolvedPO

RejectResult
├─ ok: bool
```

**External Integrations:**

```txt
Gmail API          Fetch unread emails, send replies with attachments
Azure AI Search    Vector search for product SKU matching (planned)
Airtable CRM       Product catalog, customer data, order/invoice records
Slack Webhooks     Operations team notifications for orders and exceptions
Azure Blob Storage Invoice PDF storage (planned)
```

## Cost Estimate

Running 24/7 with light usage: **~$115-170/month**

- Azure AI Search: ~$75/month
- Azure OpenAI: ~$20-50/month
- Container Apps: ~$15-30/month
- Storage & Other: ~$5-15/month

## Tech Stack

- **Backend**: Python 3.11+
- **Framework**: Custom agent framework with async workflow builder
- **AI**: Azure OpenAI (GPT-4o-mini for reasoning, text-embedding-3-large planned)
- **Auth**: Azure CLI credential for local dev, Managed Identity for production
- **Search**: Azure AI Search (vector search for SKU matching)
- **Storage**: Azure Blob Storage (invoice PDFs), Airtable (CRM/catalog)
- **Email**: Gmail API with OAuth 2.0
- **Messaging**: Slack Incoming Webhooks
- **Infrastructure**: Azure Bicep templates
- **Hosting**: Azure Container Apps (planned)
- **Observability**: Custom observability setup with workflow streaming

## Contributing

This is a weekend proof-of-concept demo project.

## License

MIT License
