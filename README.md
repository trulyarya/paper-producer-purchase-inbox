# PaperCo O2C Email Intake Demo

AI-powered Order-to-Cash system that converts purchase order emails into invoices using Azure AI agents.

## What This Does

1. Monitors Gmail inbox for purchase order emails
2. Uses a multi-agent workflow (orchestrated by Azure AI Foundry Agent Service) to process orders:
   - **Email Intake Agent**: Extracts structured data from messy PO emails
   - **SKU Resolver Agent**: Performs semantic matching to find the right products
   - **Comms and Exceptions Agent**: Drafts human-quality responses and notifications
3. Generates invoices and replies to buyers automatically
4. Sends notifications to Slack

### Multi-Agent Workflow

The system uses three specialized AI agents orchestrated through Azure AI Foundry Agent Service:

#### 1. Email Intake Agent (Extraction)

**What it does**: Reads messy PO emails from Gmail and returns strict JSON with `poNumber`, `customer`, `lines` (with `qty` and `UOM`), and `requestedDate`.

**Why an agent**: Plain code with regex or templates breaks on real-world variability, typos, mixed languages, and odd phrasing, while an LLM can generalize and still emit validated JSON with confidence scores.

#### 2. SKU Resolver Agent (Semantic Matching)

**What it does**: Maps each requested line to the best product by running semantic vector search over the catalog (Azure AI Search), then returns matched `SKU`, `UOM`, `unitPrice`, and a short rationale.

**Why an agent**: Static keyword rules and synonym lists miss near duplicates and novel wording, while an LLM-guided search can understand intent, compare close candidates, and justify the pick.

#### 3. Comms and Exceptions Agent (Human-Quality Messaging)

**What it does**: Drafts the buyer reply that includes totals, promise date, and invoice attachment, and creates a Slack Block Kit message for the operator in the orders channel.

**Why an agent**: Ensures consistent, professional communication that adapts to the context of each order, handles edge cases gracefully, and maintains brand voice.

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

## Cost Estimate

Running 24/7 with light usage: **~$115-170/month**

- Azure AI Search: ~$75/month
- Azure OpenAI: ~$20-50/month
- Container Apps: ~$15-30/month
- Storage & Other: ~$5-15/month

## Tech Stack

- **Backend**: Python, FastAPI
- **AI**: Azure AI Foundry (GPT-5-mini, text-embedding-3-large)
- **Search**: Azure AI Search (vector search)
- **Storage**: Azure Blob Storage, Airtable
- **Infrastructure**: Azure Bicep
- **Hosting**: Azure Container Apps

## Current Status

- [x] Project planning and PRD
- [x] Azure infrastructure (Bicep)
- [x] Slack Webhook URL
- [x] Airtable base schema and setup (incl. rows of sample data): As our "fake" CRM
- [x] Gmail integration and API setup
- [ ] FastAPI application
- [ ] AI agent implementations
- [ ] Testing and validation

## Contributing

This is a weekend proof-of-concept demo project.

## License

MIT License
