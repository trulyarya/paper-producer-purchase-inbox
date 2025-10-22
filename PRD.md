# PaperCo O2C Email Intake Demo PRD

## 1. Purpose

- Deliver a weekend proof-of-concept that converts unstructured purchase order emails into invoices and buyer replies with real integrations.
- Validate that a lean multi-agent approach plus deterministic services can cover messy intake, SKU matching, and polished communications.

## 2. Goals

### 2.1 Objectives

- Achieve live Gmail intake through invoice reply with the same thread handling.
- Showcase agent-led extraction, semantic SKU resolution, and natural buyer messaging.
- Operate from a single containerized Python FastAPI app with one lightweight agent service.

### 2.2 Non-Goals

- ERP, tax, carrier, or production-scale integrations.
- Enterprise-grade auth or secret rotation beyond simple bearer keys.
- Advanced credit logic or fulfillment orchestration.

## 3. Success Metrics

- Median email-to-invoice cycle completes in under two minutes across five sample emails.
- At least one messy line item matches a catalog SKU with vector score ≥ 0.75.
- Buyer receives a Gmail reply with a valid PDF invoice attachment.
- Slack notification message renders with correct totals and promise date.
- Logs capture agent reasoning, SKU candidates, totals, and enforce idempotency by Gmail message id.

## 4. Users and Use Cases

- **Buyer**: Sends a free-form PO email and expects a timely, accurate invoice reply.
- **Sales Operator**: Monitors Slack alerts and intervenes when flagged by low confidence.
- **Demo Host**: Runs the PoC, observes bot reasoning outputs, and validates metrics.

## 5. Scope

### 5.1 In Scope

- Gmail inbox polling, thread-based reply with invoice attachment.
- Airtable for all data storage (products, customers, inventory, orders, invoices), Azure AI Search vector index, Azure AI Foundry for reasoning/embeddings.
- Slack notification via incoming webhook.
- Azure Blob Storage for generated PDFs.

### 5.2 Out of Scope

- Production hardening (HA, monitoring, scale-out).
- Non-Azure AI stacks or alternative catalogs.
- Large dataset performance validation or stress testing.

## 6. Solution Overview

### 6.1 Architecture Snapshot

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

### 6.2 Key Components

- **Azure Container Apps / FastAPI**: Single backend handling orchestration, deterministic services, Airtable writes, and integrations.
- **Azure AI Foundry Agent Service**: Hosts the three domain agents with shared prompt scaffolding and guardrails.
- **Azure AI Foundry & AI Search**: Provide reasoning, embeddings, and semantic SKU retrieval.
- **Data Stores**: Airtable for all business data (products, customers, inventory, orders, invoices), Azure Blob for invoice PDFs.
- **Security**: Secrets (Airtable API key, Gmail credentials, Slack webhook URL) stored as environment variables or Azure App Configuration.

## 7. Agent Responsibilities

- **Email Intake Agent**: Normalize HTML/text emails into validated JSON (`poNumber`, customer block, line items with qty/UOM, requested date). Justified by variability and typo tolerance needs.
- **SKU Resolver Agent**: Runs hybrid search against Azure AI Search results, selects best SKU per line, emits unit price/UOM/rationale to surface confidence.
- **Comms & Exceptions Agent**: Drafts buyer-facing reply (totals, promise date, invoice attachment note) and crafts Slack message with Block Kit formatting when low confidence or business rule exceptions trigger.

## 8. Deterministic Services

- **Pricing Service**: Deterministic total calculation using catalog price and optional flat shipping.
- **Credit Check**: Simple limit minus open AR with pass/fail flag.
- **Available-to-Promise (ATP)**: Confirms inventory and returns promise date (2-day default, 5-day with shortage note).
- **Invoice Service**: Renders HTML template to PDF, saves to Blob, returns URL + metadata.
- **Email Sender**: Replies within original Gmail thread with agent-authored body and PDF attachment.
- **Slack Notifier**: Posts Block Kit message via incoming webhook with totals, status, rationale snippet.
- Note: Agents never perform state-changing calls; deterministic services enforce auditability.

## 9. Data Model

All data stored in Airtable bases with the following tables:

- **products**: `sku`, `title`, `description`, `uom`, `unit_price`, `attributes`
- **customers**: `id`, `name`, `email`, `address`, `credit_limit`, `open_ar`
- **inventory**: `sku`, `qty_available`, `location`
- **orders**: `orderId`, `poNumber`, `customer_json`, `lines_json`, `totals`, `status`, `timestamps`
- **invoices**: `invoiceId`, `orderId`, `amount`, `currency`, `pdf_blob_url`, `status`, `sentAt`

Product data is synced to Azure AI Search vector index via scheduled job or webhook for semantic SKU matching.

## 10. End-to-End Flow (Happy Path)

- **Intake**: FastAPI polls Gmail unread, normalizes HTML, calls Email Intake Agent, stores raw + structured payload in Airtable orders table.
- **Resolve**: For each line, hybrid search against Azure AI Search; SKU Resolver Agent confirms best match and rationale.
- **Decide**: Pricing, credit, and ATP deterministic services compute totals and promise date using Airtable data.
- **Invoice & Reply**: Invoice Service renders PDF, saves to Blob Storage; Comms Agent drafts buyer email; Email Sender replies with attachment.
- **Notify**: Slack Notifier posts summary message with key fields and confidence notes.
- **Persist & Close**: Order record updated in Airtable with status, invoice created in Airtable invoices table with Blob URL; Gmail message marked read using message id for idempotency.

## 11. Demo Script (≈90 Seconds)

- Drop a messy PO email into Gmail inbox and trigger processing.
- Show parsed JSON output alongside original email.
- Display SKU matches, pricing breakdown, and agent rationales.
- Open generated PDF invoice from Blob link.
- Refresh Gmail thread to show buyer reply with attachment.
- Show Slack channel message and discuss low-confidence escalation path.
- Repeat with clean PO to highlight straight-through speed.

## 12. Risks and Mitigations

- **Agent hallucination or invalid JSON**: Enforce JSON schema validation and retry with guardrails.
- **SKU mismatch due to sparse data**: Pre-seed vector index with curated descriptions and short rationales; fall back to manual review via Slack escalation.
- **Email threading issues**: Use Gmail message ids for idempotency and reply-to references; log failures for manual resend.
- **Demo environment fragility**: Provide runbook with restart steps and minimal configuration secrets.
