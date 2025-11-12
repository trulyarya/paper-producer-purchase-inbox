# Sample CRM Airtable Dataset

## Synthetic input for our fake CRM database to upload to Airtable

This folder contains **two AI-generated CSV tables that mimic the records you would find in a light-weight CRM** and order management stack of a paper manufacturing company. They ship with this prototype App, so we can spin up an Airtable base quickly, load the data there, and exercise read/write flows through the Airtable API without touching any real customer information, or having to set up a real third party CRM system (e.g. Salesforce, Hubspot, Dynamics 360 etc).

## What the tables represent

- **`airtable_customers.csv`**
  - **Purpose**: Company-level accounts powering onboarding checks, credit guardrails, and status badges in the UI.
  - **Fields**: `Customer ID`, `Name`, `Email`, `Billing Address`, `Shipping Address`, `Credit Limit`, `Open AR`, `Currency`, `Status`.
- **`airtable_products.csv`**
  - **Purpose**: Paper catalogue used for SKU matching and pricing calculations.
  - **Fields**: `SKU`, `Title`, `Description`, `UOM`, `Unit Price`, `Qty Available`, `Active`, `Attributes JSON`, `Last Updated`.

## How to use them in this repo

Upload both CSVs to Airtable:

```bash
python scripts/upload_sample_data.py
```

The script uploads to tables named `Products` and `Customers` by default (configurable via `AIRTABLE_PRODUCTS_TABLE` and `AIRTABLE_CUSTOMERS_TABLE` env vars).
