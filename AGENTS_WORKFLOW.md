# Purchase Order Workflow

## Quick Setup Checklist

| Step | Why it matters | Call |
|---|---|---|
| Upload sample data | Provides products and customers for the workflow | `python scripts/upload_sample_data.py` |
| Seed the products index | Azure AI Search needs the schema before uploads | `src/aisearch/azure_search_tools.create_products_index_schema()` |
| Seed the customers index | Same for customer lookups | `src/aisearch/azure_search_tools.create_customer_index_schema()` |
| Load products from Airtable | Feeds live catalog data into search | `src/aisearch/azure_search_tools.ingest_products_from_airtable()` |
| Load customers from Airtable | Makes resolver credit/customer logic work | `src/aisearch/azure_search_tools.ingest_customers_from_airtable()` |

Re-run ingestion commands whenever you change schemas or Airtable data you depend on. The fulfiller agent automatically re-syncs indexes after inventory/credit updates.

## Pipeline Map

`src/workflow/workflow.py` keeps looping through unread Gmail messages and spins up a fresh workflow via `create_workflow()` for each pass.

```txt
                              +----------------------+
                              |      Gmail Inbox     |
                              |  (unread queue poll) |
                              +----------+-----------+
                                         |
                                fetch_unread_emails()
                                         |
                                         v
+-------------------------------------------------------------------------------------------+
| email_classifier: This agent classifies incoming emails as potential purchase orders      |
|                                                                                           |
| - Agent: email_classifier (`src/agents/email_classifier.py`)                              |
| - Input schema: Email {                                                                   |
|       id: str                                                                             |
|       subject: str                                                                        |
|       sender: str                                                                         |
|       body: str                                                                           |
|   }                                                                                       |
| - Output schema: ClassifiedEmail {                                                        |
|       email: Email {id, subject, sender, body}                                            |
|       is_po: bool                                                                         |
|       reason: str                                                                         |
|   }                                                                                       |
| - Tools: emailing.gmail_tools.fetch_unread_emails                                         |
+-------------------------------------------------------------------------------------------+
              | is_po == False --> mark_email_as_read() and loop
              | is_po == True
              v
+-------------------------------------------------------------------------------------------+
| email_parser: This agent extracts relevant information from the classified PO email       |
|                                                                                           |
| - Agent: email_parser (`src/agents/email_parser.py`)                                      |
| - Input schema: ClassifiedEmail.email -> Email {                                          |
|       id: str                                                                             |
|       subject: str                                                                        |
|       sender: str                                                                         |
|       body: str                                                                           |
|   }                                                                                       |
| - Output schema: ParsedPO {                                                               |
|       email_id: str                                                                       |
|       customer_email: str                                                                 |
|       customer_company_name: str                                                          |
|       customer_billing_address: str                                                       |
|       customer_shipping_address: str                                                      |
|       line_items: list[                                                                   |
|           ProductLineItem {                                                               |
|               product_sku: str                                                            |
|               product_name: str                                                           |
|               ordered_qty: int                                                            |
|           }                                                                               |
|       ]                                                                                   |
|   }                                                                                       |
| - Tools:                                                                                  |
|     safety.prompt_shield.check_email_prompt_injection                                     |
|     safety.content_filter.check_email_content_safety                                      |
+-------------------------------------------------------------------------------------------+
              |
              |
              v
+-------------------------------------------------------------------------------------------+
| retriever: It retrieves relevant information from the database, based on the parsed email |
|                                                                                           |
| - Agent: retriever (`src/agents/retriever.py`)                                            |
| - Input schema: ParsedPO {                                                                |
|       email_id: str                                                                       |
|       customer_email: str                                                                 |
|       customer_company_name: str                                                          |
|       customer_billing_address: str                                                       |
|       customer_shipping_address: str                                                      |
|       line_items: list[                                                                   |
|           ProductLineItem {                                                               |
|               product_sku: str                                                            |
|               product_name: str                                                           |
|               ordered_qty: int                                                            |
|           }                                                                               |
|       ]                                                                                   |
|   }                                                                                       |
| - Output schema: RetrievedPO {                                                            |
|       email_id: str                                                                       |
|       customer_id: str                                                                    |
|       customer_name: str                                                                  |
|       customer_overall_credit_limit: float                                                |
|       customer_open_ar: float                                                             |
|       customer_available_credit: float (computed via @model_validator)                    |
|       items: list[                                                                        |
|           RetrievedItem {                                                                 |
|               customer_id: str                                                            |
|               customer_name: str                                                          |
|               customer_address: str                                                       |
|               product_sku: str                                                            |
|               product_name: str                                                           |
|               product_qty_available: int                                                  |
|               ordered_qty: int                                                            |
|               unit_price: float                                                           |
|               vat_rate: float                                                             |
|               product_in_stock: bool (computed via @model_validator)                      |
|               subtotal: float (computed via @model_validator)                             |
|           }                                                                               |
|       ]                                                                                   |
|       tax: float (computed via @model_validator)                                          |
|       shipping: float (computed via @model_validator)                                     |
|       subtotal: float (computed via @model_validator)                                     |
|       order_total: float (computed via @model_validator)                                  |
|       customer_can_order_with_credit: bool (computed via @model_validator)                |
|   }                                                                                       |
| - Tools:                                                                                  |
|     aisearch.azure_search_tools.search_customers                                          |
|     aisearch.azure_search_tools.search_products                                           |
+-------------------------------------------------------------------------------------------+
              |
              |
              v
+-------------------------------------------------------------------------------------------+
| decider: This agent makes a decision on whether to fulfill the order or if unfulfillable  |
|                                                                                           |
| - Agent: decider (`src/agents/decider.py`)                                                |
| - Input schema: RetrievedPO {                                                             |
|       email_id: str                                                                       |
|       customer_id: str                                                                    |
|       customer_name: str                                                                  |
|       customer_overall_credit_limit: float                                                |
|       customer_open_ar: float                                                             |
|       customer_available_credit: float (computed)                                         |
|       items: list[                                                                        |
|           RetrievedItem {                                                                 |
|               customer_id: str                                                            |
|               customer_name: str                                                          |
|               customer_address: str                                                       |
|               product_sku: str                                                            |
|               product_name: str                                                           |
|               product_qty_available: int                                                  |
|               ordered_qty: int                                                            |
|               unit_price: float                                                           |
|               vat_rate: float                                                             |
|               product_in_stock: bool (computed)                                           |
|               subtotal: float (computed)                                                  |
|           }                                                                               |
|       ]                                                                                   |
|       tax: float (computed)                                                               |
|       shipping: float (computed)                                                          |
|       subtotal: float (computed)                                                          |
|       order_total: float (computed)                                                       |
|       customer_can_order_with_credit: bool (computed)                                     |
|   }                                                                                       |
| - Output schema: Decision {                                                               |
|       status: Literal['FULFILLABLE', 'UNFULFILLABLE']                                     |
|       reason: str                                                                         |
|       input_payload: RetrievedPO {                                                        |
|           email_id: str                                                                   |
|           customer_id: str                                                                |
|           customer_name: str                                                              |
|           customer_overall_credit_limit: float                                            |
|           customer_open_ar: float                                                         |
|           customer_available_credit: float (computed)                                     |
|           items: list[                                                                    |
|               RetrievedItem {                                                             |
|                   customer_id: str                                                        |
|                   customer_name: str                                                      |
|                   customer_address: str                                                   |
|                   product_sku: str                                                        |
|                   product_name: str                                                       |
|                   product_qty_available: int                                              |
|                   ordered_qty: int                                                        |
|                   unit_price: float                                                       |
|                   vat_rate: float                                                         |
|                   product_in_stock: bool (computed)                                       |
|                   subtotal: float (computed)                                              |
|               }                                                                           |
|           ]                                                                               |
|           tax: float (computed)                                                           |
|           shipping: float (computed)                                                      |
|           subtotal: float (computed)                                                      |
|           order_total: float (computed)                                                   |
|           customer_can_order_with_credit: bool (computed)                                 |
|       }                                                                                   |
|   }                                                                                       |
| - Tools: (none, LLM-only evaluation)                                                      |
+-------------------------------------------------------------------------------------------+
                                                    |
                                                    |
                                                    v
              +----------------------------------------------------------------+
              |                                                                |
    Decision == FULFILLABLE                                          Decision == UNFULFILLABLE
              |                                                                |
              v                                                                v
+----------------------------------------------------------------+    +------------------------------------+
| fulfiller: fulfills the order                                  |    | rejector: rejects the order        |
|                                                                |    |                                    |
| - Agent: fulfiller                                             |    | - Agent: rejector                  |
|   (`src/agents/fulfiller.py`)                                  |    |   (`src/agents/rejector.py`)       |
| - Input schema: Decision {                                     |    | - Input schema: Decision {         |
|       status: 'FULFILLABLE'                                    |    |       status: 'UNFULFILLABLE'      |
|       reason: str                                              |    |       reason: str                  |
|       input_payload: RetrievedPO {...}                         |    |       input_payload: RetrievedPO   |
|   }                                                            |    |   }                                |
| - Output schema:                                               |    | - Output schema:                   |
|     FulfillmentResult {                                        |    |     RejectResult {                 |
|       ok: bool                                                 |    |       rejection_messaging_complete |
|       order_id: str                                            |    |   }                                |
|       invoice_no: str                                          |    | - Tools:                           |
|   }                                                            |    |     emailing.gmail_tools           |
| - Tools:                                                       |    |       .respond_unfulfillable_email |
|     fulfiller.send_confirmation_email_with_approval            |    |                                    |
|       (BLOCKS for human Slack approval, then sends email)      |    |                                    |
|     crm.airtable_tools.add_new_customer                        |    |                                    |
|     crm.airtable_tools.update_inventory                        |    |                                    |
|     crm.airtable_tools.update_customer_credit                  |    |                                    |
|     aisearch.azure_search_tools.ingest_customers_from_airtable |    |                                    |
|     aisearch.azure_search_tools.ingest_products_from_airtable  |    |                                    |
|     invoice.invoice_tools.generate_invoice_pdf_url             |    |                                    |
|                                                                |    |                                    |
+----------------------------------------------------------------+    +------------------------------------+
                        |                                                      |
                        +------------------------------------------------------+
                                                     |
                                                     v
                                   emailing.gmail_tools.mark_email_as_read()
                                                     |
                                                     v
                                 workflow loops back for the next unread message
```

## Stage Cheat Sheet

| Stage | Agent & file | Input | Output | Core tools wired |
|---|---|---|---|---|
| 0 | `classifier` (`src/agents/email_classifier.py`) | Unread Gmail message pulled via `emailing.gmail_tools.fetch_unread_emails()` | `ClassifiedEmail` (`email`, `is_po`, `reason`) | `emailing.gmail_tools.get_unread_emails` |
| 1 | `parser` (`src/agents/email_parser.py`) | `ClassifiedEmail.email` | `ParsedPO` (customer profile + line items) | `safety.prompt_shield.check_email_prompt_injection`, `safety.content_filter.check_email_content_safety` |
| 2 | `retriever` (`src/agents/retriever.py`) | `ParsedPO` | `RetrievedPO` (resolved customer, priced items, computed totals) | `aisearch.azure_search_tools.search_customers`, `aisearch.azure_search_tools.search_products` |
| 3 | `decider` (`src/agents/decider.py`) | `RetrievedPO` | `Decision` (`FULFILLABLE` or `UNFULFILLABLE` + reason + input_payload) | (LLM only, no tools) |
| 4A | `fulfiller` (`src/agents/fulfiller.py`) | `Decision` where status is `FULFILLABLE` | `FulfillmentResult` (ok, order_id, invoice_no) | `send_confirmation_email_with_approval` (blocking Slack approval + email), `add_new_customer`, `update_inventory`, `update_customer_credit`, `ingest_products_from_airtable`, `ingest_customers_from_airtable`, `generate_invoice_pdf_url` |
| 4B | `rejector` (`src/agents/rejector.py`) | `Decision` where status is `UNFULFILLABLE` | `RejectResult` (rejection_messaging_complete) | `respond_unfulfillable_email` |

## Key Behaviors

- **Classifier** must call `get_unread_emails()` exactly once and preserve the Gmail `id`; everything downstream relies on it.
- **Parser** runs safety checks FIRST via `check_email_prompt_injection()` and `check_email_content_safety()` before parsing. If threats detected, returns `SECURITY_VIOLATION` in all fields to halt the workflow.
- **Retriever** is the first place you enrich with search, pricing, and credit signals. All computed fields use `@model_validator(mode="after")`:
  - Per-item: `product_in_stock` (product_qty_available >= ordered_qty), `subtotal` (ordered_qty * unit_price)
  - Per-order: `customer_available_credit` (credit_limit - open_ar), `tax`, `shipping`, `subtotal`, `order_total`, `customer_can_order_with_credit`
- **Decider** evaluates `customer_can_order_with_credit` (must be True) and `product_in_stock` (must be True for all items). LLM-only evaluation, no tools.
- **Decision schema** uses `input_payload` (not `payload`) to contain the full `RetrievedPO` object for downstream agents.
- **Fulfiller** implements human-in-the-loop approval via blocking pattern:
  - Calls `send_confirmation_email_with_approval()` which BLOCKS execution
  - Posts to Slack and waits for human reply ('approve' or 'deny')
  - If approved: sends confirmation email immediately, then updates inventory/credit
  - If denied: returns without sending email or updating systems
  - After approval, syncs data back to Azure AI Search via `ingest_products_from_airtable()` and `ingest_customers_from_airtable()`
- **Rejector** sends polite rejection emails via `respond_unfulfillable_email()` with decider's rationale. No Slack notifications for rejections.

## Runtime Anchors

- `src/workflow/workflow.py:create_workflow()` wires `WorkflowBuilder` with the conditional edges shown above.
- `src/workflow/workflow.py:run_till_mail_read()` drives the polling loop and calls `emailing.gmail_tools.mark_email_as_read()` after each pass.

## Fulfillment Sequence (Human-in-the-Loop Approval)

When `decider` marks an order as `FULFILLABLE`, the fulfiller executes this sequence:

### 1. Generate Invoice

- Calls `generate_invoice_pdf_url(input_payload)` to create PDF invoice
- Uploads to Azure Blob Storage and returns public URL

### 2. Request Human Approval (BLOCKING)

- Calls `send_confirmation_email_with_approval(message_id, invoice_url, input_payload)`
- **This tool BLOCKS execution** and performs:
  1. Posts order summary to Slack via `post_approval_request()`
  2. Polls Slack thread every 2 seconds via `get_approval_from_slack()`
  3. Waits for human to reply with 'approve' or 'deny' keywords (case-insensitive)
  4. Timeout: 60 seconds (configurable), defaults to DENY if no response
- **If approved:** Immediately sends confirmation email via `respond_confirmation_email()`, returns `{"status": "approved", "email_sent": "true"}`
- **If denied:** Returns `{"status": "denied", "email_sent": "false"}` without sending email

### 3. Update Systems (Only if Approved)

- **New customer handling:** If `customer_id='NEW'`, calls `add_new_customer()` first, then `ingest_customers_from_airtable()`
- **Inventory updates:** Loops through items and calls `update_inventory(ordered_qty, product_sku)` for each
- **Credit updates:** Calls `update_customer_credit(customer_id, order_total)` to adjust credit exposure
- **Sync search indexes:** Calls `ingest_products_from_airtable()` and `ingest_customers_from_airtable()` to keep Azure AI Search synchronized with CRM

### 4. Return Result

- Returns `FulfillmentResult` with `ok=True`, `order_id`, and `invoice_no`

**Critical Notes:**

- The approval mechanism is implemented INSIDE the `send_confirmation_email_with_approval` tool using a blocking pattern
- This is necessary because the agent framework's `approval_mode="always_require"` doesn't work with workflows (only single agents)
- The tool handles both approval AND email sending atomically - email can only be sent after approval
- No separate Slack notification tool is called; the approval request serves as the notification

## Rejection Flow

The rejector executes when `decider` marks an order as `UNFULFILLABLE`:

1. **Read decision context:** Extract the `reason` field from Decision and `email_id` from `input_payload` (RetrievedPO)
2. **Compose rejection message:** LLM drafts a professional, clear explanation covering:
   - Why the order cannot be fulfilled (credit issues, unavailable items, etc.)
   - Suggested next steps the customer can take (e.g., reduce order quantity, resolve outstanding invoices)
3. **Send rejection email:** Calls `respond_unfulfillable_email(message_id, reason, retrieved_po)` to send rejection email in Gmail thread
4. **Return result:** Returns `RejectResult` with `rejection_messaging_complete=True`

**Note:** No Slack notifications are sent for rejections - only fulfilled orders trigger Slack approval workflows and subsequent notifications.
