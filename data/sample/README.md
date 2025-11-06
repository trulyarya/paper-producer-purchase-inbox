# Sample CRM Airtable Dataset

## Synthetic input for our fake CRM database to upload to Airtable

This folder contains **five AI-generated CSV tables that mimic the records you would find in a light-weight CRM** and order management stack of a paper manufacturing company. They ship with this prototype App, so we can spin up an Airtable base quickly, load the data there, and exercise read/write flows through the Airtable API without touching any real customer information, or having to set up a real third party CRM system (e.g. Salesforce, Hubspot, Dynamics 360 etc).

## What the tables represent

- **`airtable_customers.csv`**
  - **Purpose**: Company-level accounts powering onboarding checks, credit guardrails, and status badges in the UI.
  - **Fields**: `Customer ID`, `Name`, `Email`, `Billing Address`, `Shipping Address`, `Credit Limit`, `Open AR`, `Currency`, `Status`.
- **`airtable_products.csv`**
  - **Purpose**: Paper catalogue used for SKU matching and pricing calculations.
  - **Fields**: `SKU`, `Title`, `Description`, `UOM`, `Unit Price`, `Qty Available`, `Active`, `Attributes JSON`, `Last Updated`.
- **`airtable_orders.csv`**
  - **Purpose**: Top-level sales orders originating from Gmail leads, tying each request back to a customer and expected invoice.
  - **Fields**: `Order ID`, `PO Number`, `Customer`, `Order Date`, `Requested Ship Date`, `Status`, `Gmail Message ID`, `Net Amount`, `Invoice`.
- **`airtable_order_lines.csv`**
  - **Purpose**: Breaks orders into specific SKUs, quantities, and pricing; includes the matching model score for review.
  - **Fields**: `Line ID`, `Order`, `Product`, `Requested Text`, `Qty`, `UOM`, `Unit Price`, `Line Total`, `Match Score`, `Notes`.
- **`airtable_invoices.csv`**
  - **Purpose**: Billing records generated from orders so finance can track payment progress.
  - **Fields**: `Invoice ID`, `Order`, `Amount Due`, `PDF URL`, `Sent At`, `Status`.

## How the tables connect

```txt
Customer ──< Orders ──< Order Lines >── Product
                 │
                 └────── Invoice
```

- Orders use the customer id (e.g., `C-1001`) from `airtable_customers.csv`.

- Order lines bridge an order id (e.g., `O-2025-0001`) to a specific SKU from `airtable_products.csv`.
- Each invoice entry maps one-to-one with an order so finance status updates can be read and patched through the API.

## How to use them in this repo

- Import all five CSVs into a single Airtable base before running the prototype; the scripts expect the table names and field names to stay as-is.
- The backend code seeds Airtable with these rows and then works directly against the Airtable API, so you can safely experiment with record creation, updates, and deletes.
- Treat the data as disposable: regenerate or reset the base at any time without risk, since nothing here is sensitive or tied to production systems.
