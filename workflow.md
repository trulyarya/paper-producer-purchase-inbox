# Purchase Order Workflow

## Quick Setup Checklist

| Step | Why it matters | Call |
|---|---|---|
| Seed the products index | Azure AI Search needs the schema before uploads | `src/ai-search/azure_search_tools.create_products_index_schema()` |
| Seed the customers index | Same for customer lookups | `src/ai-search/azure_search_tools.create_customer_index_schema()` |
| Load products from Airtable | Feeds live catalog data into search | `src/ai-search/azure_search_tools.ingest_products_from_airtable()` |
| Load customers from Airtable | Makes resolver credit/customer logic work | `src/ai-search/azure_search_tools.ingest_customers_from_airtable()` |

Re-run these whenever you change schemas or Airtable data you depend on.

## Pipeline Map

`src/workflow/workflow.py` keeps looping through unread Gmail messages and spins up a fresh workflow via `create_workflow()` for each pass.

<div style="text-align:center;margin:1.5rem 0;">
<pre style="display:inline-block;text-align:left;padding:1.25rem 1.5rem;border:1px solid #d1d9e6;border-radius:16px;background:#0f172a;color:#e2e8f0;line-height:1.5;font-family:'Fira Code',Menlo,Consolas,monospace;font-size:0.95rem;">
<span style="color:#38bdf8;">                         +=====================+</span>
<span style="color:#38bdf8;">                         |     Gmail Inbox     |</span>
<span style="color:#38bdf8;">                         |     (unread queue)  |</span>
<span style="color:#38bdf8;">                         +==========+==========+</span>
<span style="color:#94a3b8;">                                    |</span>
<span style="color:#cbd5f5;">                        fetch_unread_emails()</span>
<span style="color:#94a3b8;">                                    |</span>
<span style="color:#94a3b8;">                                    v</span>
<span style="color:#c4b5fd;">        +---------------------------+---------------------------+</span>
<span style="color:#c4b5fd;">        |                        classifier                     |</span>
<span style="color:#c4b5fd;">        |  emits ClassifiedEmail (is_po flag, email.id saved)   |</span>
<span style="color:#c4b5fd;">        +-----------+---------------------------+---------------+</span>
<span style="color:#94a3b8;">                    |                           |</span>
<span style="color:#fca5a5;">                    | is_po == False            |</span>
<span style="color:#94a3b8;">                    |                           v</span>
<span style="color:#fca5a5;">     mark_email_as_read()</span><span style="color:#94a3b8;">              +-------------------------+</span>
<span style="color:#fca5a5;">          and loop next                </span><span style="color:#34d399;">|         parser          |</span>
<span style="color:#94a3b8;">                    |                  </span><span style="color:#34d399;">|  ClassifiedEmail.email  |</span>
<span style="color:#94a3b8;">                    |                  </span><span style="color:#34d399;">|        -> ParsedPO      |</span>
<span style="color:#94a3b8;">                    |                  </span><span style="color:#34d399;">+-----------+-------------+</span>
<span style="color:#94a3b8;">                    |                              |</span>
<span style="color:#94a3b8;">                    |                              v</span>
<span style="color:#34d399;">                    |                  +-------------------------+</span>
<span style="color:#34d399;">                    |                  |         resolver        |</span>
<span style="color:#34d399;">                    |                  | ParsedPO + check_credit |</span>
<span style="color:#34d399;">                    |                  |        -> ResolvedPO    |</span>
<span style="color:#34d399;">                    |                  +-----------+-------------+</span>
<span style="color:#94a3b8;">                    |                              |</span>
<span style="color:#94a3b8;">                    |                              v</span>
<span style="color:#facc15;">                    |                  +-------------------------+</span>
<span style="color:#facc15;">                    |                  |         decider         |</span>
<span style="color:#facc15;">                    |                  |    ResolvedPO ->        |</span>
<span style="color:#facc15;">                    |                  | FULFILLABLE / UNFULFILL |</span>
<span style="color:#facc15;">                    |                  +-----+-----------+-------+</span>
<span style="color:#94a3b8;">                    |                        |           |</span>
<span style="color:#94a3b8;">                    |                        |           |</span>
<span style="color:#34d399;">                    |               FULFILLABLE      </span><span style="color:#f87171;">UNFULFILLABLE</span>
<span style="color:#94a3b8;">                    |                        |           |</span>
<span style="color:#94a3b8;">                    |                        v           v</span>
<span style="color:#22d3ee;">                    |             +----------------+  +----------------+</span>
<span style="color:#22d3ee;">                    |             |    fulfiller   |  |    rejector    |</span>
<span style="color:#22d3ee;">                    |             |   (happy path) |  | (unhappy path) |</span>
<span style="color:#22d3ee;">                    |             +--------+-------+  +--------+-------+</span>
<span style="color:#94a3b8;">                    |                      |                    |</span>
<span style="color:#94a3b8;">                    +----------------------+--------------------+</span>
<span style="color:#94a3b8;">                                           |</span>
<span style="color:#94a3b8;">                                           v</span>
<span style="color:#38bdf8;">                         +===============================+</span>
<span style="color:#38bdf8;">                         | mark_email_as_read() and loop |</span>
<span style="color:#38bdf8;">                         +===============================+</span>
</pre>
</div>

## Stage Cheat Sheet

| Stage | Agent & file | Input | Output | Core helpers already wired |
|---|---|---|---|---|
| 0 | `classifier` (`src/agents/classifier.py`) | Unread Gmail message pulled via `emailing.gmail_tools.fetch_unread_emails()` | `ClassifiedEmail` (`email`, `is_po`, `reason`) | `emailing.gmail_tools.fetch_unread_emails()` |
| 1 | `parser` (`src/agents/parser.py`) | `ClassifiedEmail.email` | `ParsedPO` (customer profile + line items) | _None registered yet (keep `clean_email_payload` in reserve)_ |
| 2 | `resolver` (`src/agents/resolver.py`) | `ParsedPO` | `ResolvedPO` (resolved customer, priced items, computed totals) | `agents.resolver.check_credit()` |
| 3 | `decider` (`src/agents/decider.py`) | `ResolvedPO` | `Decision` (`FULFILLABLE` or `UNFULFILLABLE` + reason + payload) | (LLM only) |
| 4A | `fulfiller` (`src/agents/fulfiller.py`) | `Decision` where status is `FULFILLABLE` | `FulfillmentResult` (success flag, order id, invoice ref) | `update_inventory`, `update_customer_credit`, `add_order_to_crm`, `generate_invoice`, `send_slack_notification` |
| 4B | `rejector` (`src/agents/rejector.py`) | `Decision` where status is `UNFULFILLABLE` | `RejectResult` | — |

## Key Behaviors

- The classifier must call `fetch_unread_emails()` exactly once and preserve the Gmail `id`; everything downstream relies on it.
- Parser focuses on structure only; resolver is the first place you enrich with search, pricing, and credit signals.
- Resolver totals (`subtotal`, `tax`, `shipping`, `order_total`) are computed fields on `ResolvedPO`, so later agents do not recalc.
- Decider routes based on availability and credit; the workflow edges mirror `should_fulfill()` and `should_reject()` in `src/workflow/workflow.py`.

## Runtime Anchors

- `src/workflow/workflow.py:create_workflow()` wires `WorkflowBuilder` with the conditional edges shown above.
- `src/workflow/workflow.py:run_till_mail_read()` drives the polling loop and calls `emailing.gmail_tools.mark_email_as_read()` after each pass.

## Helper Library (wire up when ready)

- `emailing.gmail_tools.respond_confirmation_email()` — compose and send the happy-path reply (make it a tool for `fulfiller` when messaging is ready).
- `emailing.gmail_tools.respond_unfulfillable_email()` — notify customers about rejects.
- `agents.fulfiller.send_slack_notification()` — Slack notifier used by the fulfiller (fulfilled orders only).
