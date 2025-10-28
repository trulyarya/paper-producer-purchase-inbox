# Workflow Overview

```asciidoc
###########################################
SETUP: Data Sync to Azure AI Search Indexes
###########################################

Module: ai-search/azure_search_tools.py

1. create_products_index_schema()      # Define product index schema
2. create_customer_index_schema()      # Define customer index schema
3. ingest_products_from_airtable()     # Airtable → AI Search (Products)
4. ingest_customers_from_airtable()    # Airtable → AI Search (Customers)

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│ STAGE 0: classifier Agent                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
INPUT:  Raw Gmail email
OUTPUT: ClassifiedEmail (is_po flag + rationale)

Agent: classifier
Tools:
- fetch_unread_emails()                    # gmail_tools.fetch_unread_emails

Notes:
- Agent prompts call this helper once, pick the first unread email, and emit the Pydantic ClassifiedEmail.
- Original Gmail message id must be preserved so downstream agents can reply.

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│ STAGE 1: parser Agent                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
INPUT:  ClassifiedEmail.email
OUTPUT: ParsedPO (structured customer + line items)

Agent: parser
Tools:
- (optional) clean_email_payload()        # ai_function placeholder when normalisation is needed

Behavior:
- Produces ParsedPO with customer + line_items, leveraging Pydantic validation for required fields.
- No totals are computed here; computed fields live on ResolvedPO.

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│ STAGE 2: resolver Agent (Customer & SKU Resolution)          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
INPUT:  ParsedPO
OUTPUT: ResolvedPO

Agent: resolver
Tools (callable via ai_functions or simple wrappers):
- search_customers(query)                 # azure_search_tools.search_customers
- search_products(query)                  # azure_search_tools.search_products
- create_customer(...)                    # crm.airtable_tools.create_customer
- check_credit(customer_name, order_total)

Process:
2.1 Customer Resolution
    a. Query Azure Search with ParsedPO customer hints.
    b. If no confident hit: create_customer(...) and trigger background re-ingestion of the Customers index.
    c. Carry the chosen/created customer_id + contact metadata into ResolvedPO.

2.2 Product Resolution
    For each ParsedPO.line_items entry:
    - search_products(line.product_name) for candidate SKUs.
    - Select best match with sufficient inventory.
    - Populate ResolvedItem (sku, title, price, qtyAvailable, ordered_qty, etc).
    - Set product_availability flag from qtyAvailable vs ordered_qty.

2.3 Credit Check
    - Use ResolvedPO.computed subtotal/tax/shipping/order_total (Pydantic computed fields) to call check_credit().
    - Set customer_credit_ok boolean from the tool response.

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│ STAGE 3: decider Agent                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
INPUT:  ResolvedPO
OUTPUT: Decision (FULFILLABLE / UNFULFILLABLE)

Agent: decider
Tools: None (LLM evaluates resolved payload)

Decision criteria (implemented in prompt):
- customer_credit_ok == True
- All ResolvedItem.product_availability == True
- Resolver supplied confident matches (include Azure Search scores in payload if available)
- Reason field explains the verdict.

Routing:
- FULFILLABLE  → Stage 4A (fulfiller)
- UNFULFILLABLE → Stage 4B (rejector)

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│ STAGE 4A: fulfiller Agent (Happy Path)                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
Agent: fulfiller
Tools executed in order:
1. update_inventory(order_lines)          # decrement stock (currently queues work)
2. update_customer_credit(customer_id, order_total)
3. generate_invoice(resolved_po)          # wraps invoice_tools.generate_invoice_pdf_url
4. add_order_to_crm(resolved_po, invoice_pdf_url)
5. respond_confirmation_email(message_id, pdf_url)   # gmail_tools.respond_confirmation_email
6. send_slack_notification(resolved_po, order_id, invoice_url)

Operational Notes:
- ResolvedPO already supplies subtotal/tax/shipping/order_total via computed fields; no new math functions needed.
- respond_confirmation_email expects the original Gmail message_id kept from Stage 0.
- update_* helpers return ack payloads; integrate with actual services or job queues later.

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│ STAGE 4B: rejector Agent (Unhappy Path)                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
Agent: rejector
Tools:
- respond_unfulfillable_email(message_id, reason)   # gmail_tools.respond_unfulfillable_email
- send_slack_notification(...)                      # optional ops alert

Flow:
- Identify root cause (credit exceeded, out of stock, product not found, low confidence).
- Draft polite reply with next steps and send via Gmail reply helper.
- Optionally notify Slack with the rejection context.

```

Entry Points
------------
- `agents.create_workflow()` wires the DAG with conditional edges.
- `agents.run_till_mail_read()` polls Gmail, feeds each unread email through the workflow, and marks it read.

Implementation Notes
--------------------
- Pydantic models (`Email`, `ParsedPO`, `ResolvedPO`, `Decision`, etc.) enforce structure and compute totals, keeping auxiliary helpers minimal.
- Azure Search schemas and Airtable sync jobs must be run before the agents to ensure fresh indexes.
- When a new customer is created, schedule a follow-up ingestion (step 3 or 4 in setup) so future searches resolve immediately.
