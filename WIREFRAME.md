# Lo-Fi Wireframe

## PaperCo O2C Email Automation

---

## System Overview

No traditional UI - uses existing platforms:

```txt
Customer (Email) → System (AI Agents) → Sales Ops (Slack)
```

---

## 1. Email Layouts

### Input: Customer PO Email

```txt
┌─────────────────────────────┐
│ From: [customer email]      │
│ Subject: PO #XXX            │
├─────────────────────────────┤
│ Order details:              │
│ • Product list              │
│ • Quantities                │
│ • Shipping address          │
└─────────────────────────────┘
```

### Output: Confirmation Email

```txt
┌─────────────────────────────┐
│ Subject: Re: PO #XXX        │
├─────────────────────────────┤
│ Thank you message           │
│                             │
│ [Order summary table]       │
│ • Line items                │
│ • Totals                    │
│                             │
│ [PDF attachment]            │
└─────────────────────────────┘
```

### Output: Rejection Email

```txt
┌─────────────────────────────┐
│ Subject: Re: PO #XXX        │
├─────────────────────────────┤
│ Reason for rejection        │
│                             │
│ [Problem details]           │
│                             │
│ Next steps list             │
└─────────────────────────────┘
```

---

## 2. Slack Approval Card

```txt
┌─────────────────────────────┐
│ PaperCo Bot  [timestamp]    │
├─────────────────────────────┤
│ Order Awaiting Approval     │
│                             │
│ Customer: [name]            │
│ Total: [amount]             │
│ Items: [count]              │
│                             │
│ [Line items list]           │
│                             │
│ Reply: approve / deny       │
└─────────────────────────────┘
```

**Responses:**

- `approve` → Confirmation posted, invoice sent
- `deny` → Denial posted, no invoice
- Timeout (60s) → Auto-deny

---

## 3. Invoice PDF

```txt
┌─────────────────────────────┐
│ [Logo] Company Header       │
├─────────────────────────────┤
│ INVOICE                     │
│ Invoice #, Date, PO #       │
├─────────────────────────────┤
│ Bill To:                    │
│ [Customer details]          │
├─────────────────────────────┤
│ Item | Qty | Price | Total  │
│ ─────────────────────────   │
│ [Line items]                │
├─────────────────────────────┤
│              Subtotal: XXX  │
│              Tax: XXX       │
│              Shipping: XXX  │
│              ─────────────  │
│              TOTAL: XXX     │
├─────────────────────────────┤
│ Payment terms & bank info   │
└─────────────────────────────┘
```

---

## 4. Workflow

```txt
Email → Classify → Parse → Match → Decide
                                      ↓
                            ┌─────────┴─────────┐
                            ↓                   ↓
                        Fulfill             Reject
                            ↓                   ↓
                    Gen Invoice         Send Rejection
                    Post Slack          
                    Wait Approval       
                         ↓              
                    Send / Stop
```

---

## 5. User Flow Diagrams

### Customer Flow (Happy Path)

```txt
Customer writes PO email → Send to orders@paperco.com
                              ↓
                         Wait 2-10 minutes
                              ↓
                    Receive invoice email + PDF
```

### Customer Flow (Rejection)

```txt
Customer writes PO email → Send to orders@paperco.com
                              ↓
                         Wait 2-10 minutes
                              ↓
                  Receive rejection email with reason
```

### Sales Ops Flow (Approval)

```txt
Receive Slack notification → Review order details
                              ↓
                    Reply "approve" or "deny"
                              ↓
              See confirmation → Done
```

---

## 6. Navigation Flow

| Step | User Action | Interface | Result |
|------|-------------|-----------|--------|
| 1 | Send PO | Gmail | Processing starts |
| 2 | Wait | - | Slack notification |
| 3 | Approve/Deny | Slack | Invoice sent / stopped |
| 4 | Receive response | Gmail | PDF or rejection |

---

**Version:** 1.0 | **Created:** Nov 11, 2024
