# Purchase Order Workflow

## Quick Setup Checklist

| Step | Why it matters | Call |
|---|---|---|
| Seed the products index | Azure AI Search needs the schema before uploads | `src/aisearch/azure_search_tools.create_products_index_schema()` |
| Seed the customers index | Same for customer lookups | `src/aisearch/azure_search_tools.create_customer_index_schema()` |
| Load products from Airtable | Feeds live catalog data into search | `src/aisearch/azure_search_tools.ingest_products_from_airtable()` |
| Load customers from Airtable | Makes resolver credit/customer logic work | `src/aisearch/azure_search_tools.ingest_customers_from_airtable()` |

Re-run these whenever you change schemas or Airtable data you depend on.

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
| - Tools: (none wired yet)                                                                 |
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
|       customer_open_ar: float                                                             |
|       customer_credit_limit: float                                                        |
|       items: list[                                                                        |
|           RetrievedItem {                                                                 |
|               matched_customer_id: str                                                    |
|               matched_customer_name: str                                                  |
|               matched_customer_address: str                                               |
|               matched_product_sku: str                                                    |
|               matched_product_name: str                                                   |
|               matched_product_qty_available: int                                          |
|               ordered_qty: int                                                            |
|               price: float                                                                |
|               vat_rate: float                                                             |
|               product_in_stock: bool (computed)                                           |
|               line_item_subtotal: float (computed)                                        |
|           }                                                                               |
|       ]                                                                                   |
|       customer_available_credit: float (computed)                                         |
|       subtotal: float (computed)                                                          |
|       tax: float (computed)                                                               |
|       shipping: float (computed)                                                          |
|       order_total: float (computed)                                                       |
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
|       customer_open_ar: float                                                             |
|       customer_credit_limit: float                                                        |
|       items: list[                                                                        |
|           RetrievedItem {                                                                 |
|               matched_customer_id: str                                                    |
|               matched_customer_name: str                                                  |
|               matched_customer_address: str                                               |
|               matched_product_sku: str                                                    |
|               matched_product_name: str                                                   |
|               matched_product_qty_available: int                                          |
|               ordered_qty: int                                                            |
|               price: float                                                                |
|               vat_rate: float                                                             |
|               product_in_stock: bool (computed)                                           |
|               line_item_subtotal: float (computed)                                        |
|           }                                                                               |
|       ]                                                                                   |
|       customer_available_credit: float (computed)                                         |
|       subtotal: float (computed)                                                          |
|       tax: float (computed)                                                               |
|       shipping: float (computed)                                                          |
|       order_total: float (computed)                                                       |
|   }                                                                                       |
| - Output schema: Decision {                                                               |
|       status: Literal['FULFILLABLE', 'UNFULFILLABLE']                                     |
|       reason: str                                                                         |
|       input_payload: RetrievedPO {                                                        |
|           email_id: str                                                                   |
|           customer_id: str                                                                |
|           customer_name: str                                                              |
|           customer_open_ar: float                                                         |
|           customer_credit_limit: float                                                    |
|           items: list[                                                                    |
|               RetrievedItem {                                                             |
|                   matched_customer_id: str                                                |
|                   matched_customer_name: str                                              |
|                   matched_customer_address: str                                           |
|                   matched_product_sku: str                                                |
|                   matched_product_name: str                                               |
|                   matched_product_qty_available: int                                      |
|                   ordered_qty: int                                                        |
|                   price: float                                                            |
|                   vat_rate: float                                                         |
|                   product_in_stock: bool (computed)                                       |
|                   line_item_subtotal: float (computed)                                    |
|               }                                                                           |
|           ]                                                                               |
|           customer_available_credit: float (computed)                                     |
|           subtotal: float (computed)                                                      |
|           tax: float (computed)                                                           |
|           shipping: float (computed)                                                      |
|           order_total: float (computed)                                                   |
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
+----------------------------------------------------+    +------------------------------------+
| fulfiller: fulfills the order                      |    | rejector: rejects the order        |
|                                                    |    |                                    |
| - Agent: fulfiller                                 |    | - Agent: rejector                  |
|   (`src/agents/fulfiller.py`)                      |    |   (`src/agents/rejector.py`)       |
| - Input schema: Decision {                         |    | - Input schema: Decision {         |
|       status: 'FULFILLABLE'                        |    |       status: 'UNFULFILLABLE'      |
|       reason: str                                  |    |       reason: str                  |
|       input_payload: RetrievedPO {...}             |    |       input_payload: RetrievedPO   |
|   }                                                |    |   }                                |
| - Output schema:                                   |    | - Output schema:                   |
|     FulfillmentResult {                            |    |     RejectResult {                 |
|       ok: bool                                     |    |       rejection_messaging_complete |
|       order_id: str                                |    |   }                                |
|       invoice_no: str                              |    | - Tools:                           |
|   }                                                |    |     emailing.gmail_tools           |
| - Tools:                                           |    |       .respond_unfulfillable_email |
|     crm.airtable_tools.update_inventory            |    |                                    |
|     crm.airtable_tools.update_customer_credit      |    |                                    |
|     crm.airtable_tools.add_new_customer            |    |                                    |
|     aisearch.azure_search_tools                    |    |                                    |
|       .ingest_products_from_airtable               |    |                                    |
|     aisearch.azure_search_tools                    |    |                                    |
|       .ingest_customers_from_airtable              |    |                                    |
|     invoice.invoice_tools.generate_invoice         |    |                                    |
|     emailing.gmail_tools                           |    |                                    |
|       .respond_confirmation_email                  |    |                                    |
|     messaging.slack_msg_sender                     |    |                                    |
|       .post_slack_message                          |    |                                    |
+----------------------------------------------------+    +------------------------------------+
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

| Stage | Agent & file | Input | Output | Core helpers already wired |
|---|---|---|---|---|
| 0 | `classifier` (`src/agents/email_classifier.py`) | Unread Gmail message pulled via `emailing.gmail_tools.fetch_unread_emails()` | `ClassifiedEmail` (`email`, `is_po`, `reason`) | `emailing.gmail_tools.fetch_unread_emails()` |
| 1 | `parser` (`src/agents/email_parser.py`) | `ClassifiedEmail.email` | `ParsedPO` (customer profile + line items) | _None registered yet_ |
| 2 | `retriever` (`src/agents/retriever.py`) | `ParsedPO` | `RetrievedPO` (resolved customer, priced items, computed totals) | `aisearch.azure_search_tools.search_customers`, `aisearch.azure_search_tools.search_products` |
| 3 | `decider` (`src/agents/decider.py`) | `RetrievedPO` | `Decision` (`FULFILLABLE` or `UNFULFILLABLE` + reason + input_payload) | (LLM only) |
| 4A | `fulfiller` (`src/agents/fulfiller.py`) | `Decision` where status is `FULFILLABLE` | `FulfillmentResult` (success flag, order id, invoice ref) | `update_inventory`, `update_customer_credit`, `add_new_customer`, `ingest_products_from_airtable`, `ingest_customers_from_airtable`, `generate_invoice`, `respond_confirmation_email`, `post_slack_message` |
| 4B | `rejector` (`src/agents/rejector.py`) | `Decision` where status is `UNFULFILLABLE` | `RejectResult` (rejection_messaging_complete) | `respond_unfulfillable_email` |

## Key Behaviors

- The classifier must call `fetch_unread_emails()` exactly once and preserve the Gmail `id`; everything downstream relies on it.
- Parser focuses on structure only; retriever is the first place you enrich with search, pricing, and credit signals.
- Retriever totals (`subtotal`, `tax`, `shipping`, `order_total`) are computed fields on `RetrievedPO`, so later agents do not recalc.
- Retriever also includes computed fields: `customer_available_credit`, `product_in_stock`, and `line_item_subtotal`.
- Decider evaluates `customer_available_credit` (must be >= 0) and `product_in_stock` (must be True for all items).
- Decider routes based on availability and credit; the workflow edges mirror `should_fulfill()` and `should_reject()` in `src/workflow/workflow.py`.
- Decision schema uses `input_payload` (not `payload`) to contain the full `RetrievedPO` object.
- **Fulfiller now syncs data back to Azure AI Search:** After updating inventory and customer credit in Airtable, the fulfiller calls `ingest_products_from_airtable()` and `ingest_customers_from_airtable()` to keep search indexes synchronized with CRM changes.
- **Fulfiller sends confirmation emails:** The fulfiller now calls `respond_confirmation_email()` to send order confirmations to customers with invoice attachments.
- **Rejector is fully wired:** The rejector now uses `respond_unfulfillable_email()` to send professional rejection emails to customers explaining why their order cannot be fulfilled.

## Runtime Anchors

- `src/workflow/workflow.py:create_workflow()` wires `WorkflowBuilder` with the conditional edges shown above.
- `src/workflow/workflow.py:run_till_mail_read()` drives the polling loop and calls `emailing.gmail_tools.mark_email_as_read()` after each pass.

## Fulfillment Sequence

The fulfiller executes these steps in order:

1. **Update inventory:** `update_inventory(ordered_qty, product_sku)` — Deduct ordered quantities from stock levels in Airtable (called per line item)
2. **Update customer credit:** `update_customer_credit(customer_id, order_amount)` — Adjust customer's credit exposure in CRM
3. **Sync products to search:** `ingest_products_from_airtable()` — Update Azure AI Search indexes with latest inventory
4. **Sync customers to search:** `ingest_customers_from_airtable()` — Update Azure AI Search indexes with latest customer data
5. **Generate invoice:** `generate_invoice(resolved_po)` — Create PDF invoice and return its URL
6. **Send confirmation email:** `respond_confirmation_email(message_id, pdf_url)` — Email customer with order confirmation and invoice attachment
7. **Notify operations:** `post_slack_message(...)` — Alert ops team in Slack with order details and invoice link

**Note:** If customer doesn't exist, call `add_new_customer()` before processing, then sync with `ingest_customers_from_airtable()`.

## Rejection Flow

The rejector executes:

1. **Compose rejection email:** Agent uses LLM to compose a professional, clear explanation of why the order cannot be fulfilled (credit issues, unavailable items, etc.)
2. **Send rejection email:** `respond_unfulfillable_email(message_id, reason)` — Sends the rejection email to the customer with explanation
3. **Return result:** `RejectResult` with `rejection_messaging_complete=true`

**Note:** No Slack notifications are sent for rejections — only fulfilled orders trigger ops alerts.
