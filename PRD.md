# Product Requirements Document

## PaperCo Order-to-Cash Email Automation

---

## 1. Product Summary

Automated system that reads purchase order emails, validates orders, gets human approval, and sends invoices back to customers - all in under 2 minutes.

**Goal:** Eliminate manual order processing while keeping humans in control of final approvals.

**Value:** Save time, reduce errors, maintain oversight, sync data automatically.

---

## 2. Target Audience

| User | What They Do | What They Need |
|------|--------------|----------------|
| **Sales Ops** | Approve orders in Slack | Fast approval with clear details |
| **Customers** | Email purchase orders | Quick, accurate invoices |
| **Managers** | Review metrics | Processing speed visibility |

**Technical Level:** None required - runs automatically.

---

## 3. Core Features

| Feature | Purpose | How It Works |
|---------|---------|--------------|
| **Email Classification** | Identify purchase orders | AI reads Gmail, flags PO emails |
| **Security & Parsing** | Extract details safely | Blocks threats, extracts customer/products/quantities |
| **Product Matching** | Find correct SKUs | AI search handles typos, gets pricing/inventory/credit |
| **Decision Engine** | Check fulfillability | Validates inventory + credit limits |
| **Human Approval** | Final control gate | Posts to Slack, **waits** for approve/deny (60s timeout) |
| **Invoice Delivery** | Send professional docs | Generates PDF, uploads to cloud, emails customer |
| **Rejection Handling** | Decline gracefully | Explains why, suggests next steps |

---

## 4. User Interface

**No traditional UI** - uses existing tools:

- **Customers:** Regular email (Gmail, Outlook, etc.)
- **Sales Ops:** Slack mobile/desktop for approvals
- **Admins:** Terminal logs + Azure portal

**Slack Approval Format:**

```txt
📦 Order Awaiting Approval

Customer: GreenOffice GmbH
Total: EUR 1,234.56
Items: 3
- 50x Recycled Cardboard @ EUR 12.50 → EUR 625.00
- 100x Kraft Paper @ EUR 4.00 → EUR 400.00

Reply `approve` or `deny` to this message.
```

---

## 5. Navigation Flow

```txt
Customer Email → Classify → Parse → Match → Decide
                    ↓         ↓       ↓       ↓
                 Is PO?   Safe?   Found?  Can fulfill?
                    ↓         ↓       ↓       ↓
                  YES      YES     YES      YES → Generate Invoice
                                                 → Post to Slack
                                                 → WAIT for human
                                                 → If approved: Send + Update CRM
                                                 → If denied: Stop
                    
                  NO or security issue or not found or can't fulfill
                    ↓
                  Send rejection email OR ignore
```

**Decision Points:**

| Gate | Question | Pass → | Fail → |
|------|----------|--------|--------|
| Classification | Is PO? | Continue | Ignore |
| Security | Safe content? | Parse | Block & stop |
| Matching | Found items? | Decide | Use fallback |
| Decision | In stock + credit OK? | Fulfill | Reject |
| Approval | Human approved? | Send invoice | Don't send |

---

## 6. Sample Data

**Input Email:**

```txt
From: max@greenoffice.de
Subject: PO #1156

Please send:
- 50 recycled cardboard boxes
- 100 kraft paper sheets

Ship to: Hauptstrasse 42, Berlin
```

**Output Invoice Email:**

```txt
Thank you for your order!

Order Summary:
- 50x Recycled Cardboard @ EUR 12.50 = EUR 625.00
- 100x Kraft Paper @ EUR 4.00 = EUR 400.00

Subtotal: EUR 1,025.00
Tax (19%): EUR 194.75
Shipping: EUR 25.00
Total: EUR 1,244.75

[PDF Invoice attached]
```

**Rejection Email:**

```txt
Unfortunately we cannot fulfill your order:

Insufficient credit. Your limit is EUR 5,000 with 
EUR 4,800 already owed. This order (EUR 3,500) 
exceeds available credit (EUR 200).

Next steps: Pay balance or request credit increase.
```

---

## 7. Technical Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Language** | Python 3.12+ | Core application |
| **AI** | Azure OpenAI (GPT-4.1) | Agent reasoning |
| **Search** | Azure AI Search | Product/customer matching |
| **CRM** | Airtable | Product/customer data |
| **Email** | Gmail API | Inbox + replies |
| **Approval** | Slack SDK | Human-in-loop |
| **PDF** | Jinja2 + WeasyPrint | Invoice generation |
| **Storage** | Azure Blob | PDF hosting |
| **Security** | Azure Content Safety | Threat detection |

**Data Model:**

```txt
Products: SKU, Title, Description, Price, Qty Available
Customers: ID, Name, Email, Address, Credit Limit, Open AR
```

**Architecture:**

```txt
Gmail → Workflow (6 AI Agents) → Azure OpenAI + AI Search
                ↓
        Airtable CRM ← → Azure Blob (PDFs)
                ↓
        Slack Approval → Gmail Response
```

---

## 8. Styling

- **Emails:** Professional, clear, friendly tone
- **Invoices:** A4 PDF, company branding, clean tables
- **Slack:** Emoji icons, structured cards, action prompts
- **Logs:** JSON with timestamps (console + Azure Insights)

---

## 9. Use Cases

### Happy Path: Order Fulfilled

1. Customer emails order for 3 products
2. System classifies as PO, passes security
3. Finds customer (existing), matches all SKUs
4. Checks: All in stock ✓, Credit available ✓
5. Generates invoice PDF
6. Posts to Slack → Operator approves in 20s
7. Sends invoice email, updates inventory/credit
8. **Complete in 90 seconds**

### Credit Limit Exceeded

1. Order total EUR 5,000, customer has EUR 200 credit
2. System marks UNFULFILLABLE
3. Sends rejection explaining credit situation
4. Suggests: pay balance or request increase
5. **No Slack notification for rejections**

### Human Denies Approval

1. Order passes all automated checks
2. Operator notices suspicious shipping address
3. Replies "deny" in Slack
4. System blocks invoice, logs denial
5. **No email sent, no CRM updates**

### Security Threat Blocked

1. Malicious email attempts prompt injection
2. Safety check detects attack
3. Workflow terminates immediately
4. Security incident logged
5. **No customer response sent**

---

## 10. Out of Scope

**Not in MVP:** Multi-currency, partial fulfillment, order edits, returns, subscriptions, volume discounts, ERP integration, multi-language, custom pricing, shipping APIs, payment processing, automated testing, high availability, dashboards

**Why:** Focus on core workflow first; these are future enhancements.

---

## 11. Success Metrics

| Metric | Target |
|--------|--------|
| Email → Invoice time | < 2 min |
| Classification accuracy | > 95% |
| Product match accuracy | > 90% |
| Approval rate | > 80% |
| Security block rate | 100% |
| Uptime | > 99% |

---

## 12. Deployment

**Quick Start:**

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

# 2. Configure .env with Azure/Airtable/Slack credentials

# 3. Upload sample CRM data (CSV files) to Airtable
python scripts/upload_csvs_to_airtable.py

# 4. Run
python main.py
```

---

## 13. Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| AI hallucination | Human approval required |
| Wrong customer match | Semantic threshold ≥ 0.75 |
| Inventory overselling | Real-time checks before fulfillment |
| Security bypass | Multi-layer safety (prompt shield + content filter) |
| Approval timeout | 60s timeout → auto-deny |

---

## 14. Future Enhancements

**Phase 2:** Partial fulfillment, multi-currency, order modifications, web portal, real ERP integration, analytics dashboard

**Phase 3:** Subscriptions, contract pricing, international shipping, returns processing, mobile app

---

## 15. Glossary

| Term | Definition |
|------|------------|
| **AI Agent** | Software using language models for specific tasks |
| **Blocking Pattern** | Code pauses until event occurs (human approval) |
| **Open AR** | Accounts Receivable - money customer owes |
| **Prompt Injection** | Attack manipulating AI with malicious instructions |
| **SKU** | Stock Keeping Unit - unique product ID |
| **Semantic Search** | Search by meaning, not exact keywords |

---

**Version:** 1.1 | **Updated:** Nov 11, 2024 | **Status:** Active
