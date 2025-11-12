"""Create Airtable tables and populate with CSV data."""

import os
import csv
import requests
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# Environment variables
API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
BASE_DIR = Path(__file__).resolve().parents[1]

# Type converters: map field type -> Python conversion function
TYPE_CONVERTERS = {
    "currency": float,
    "number": int,
    "checkbox": lambda v: v.lower() == "true",
}

# Products table schema
PRODUCTS_SCHEMA = [
    {"name": "SKU", "type": "singleLineText"},
    {"name": "Title", "type": "singleLineText"},
    {"name": "Description", "type": "multilineText"},
    {"name": "UOM", "type": "singleLineText"},
    {"name": "Unit Price", "type": "currency", "options": {"symbol": "€", "precision": 2}},
    {"name": "Qty Available", "type": "number", "options": {"precision": 0}},
    {"name": "Active", "type": "checkbox", "options": {"color": "greenBright", "icon": "check"}},
    {"name": "Attributes JSON", "type": "multilineText"},
    {"name": "Last Updated", "type": "dateTime", "options": {
        "dateFormat": {"name": "iso", "format": "YYYY-MM-DD"},
        "timeFormat": {"name": "24hour", "format": "HH:mm"},
        "timeZone": "utc"
    }}
]

# Customers table schema
CUSTOMERS_SCHEMA = [
    {"name": "Customer ID", "type": "singleLineText"},
    {"name": "Name", "type": "singleLineText"},
    {"name": "Email", "type": "email"},
    {"name": "Billing Address", "type": "multilineText"},
    {"name": "Shipping Address", "type": "multilineText"},
    {"name": "Credit Limit", "type": "currency", "options": {"symbol": "€", "precision": 2}},
    {"name": "Open AR", "type": "currency", "options": {"symbol": "€", "precision": 2}},
    {"name": "Currency", "type": "singleLineText"},
    {"name": "Status", "type": "singleLineText"}
]


def create_table(table_name: str, fields: list[dict]) -> str | None:
    """Create a new Airtable table with the given schema."""
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {"name": table_name, "fields": fields}
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        logger.info(f"Created table: {table_name}")
        return response.json()["id"]
    
    logger.warning(f"Failed to create {table_name}: {response.status_code} - {response.text}")


def insert_records(table_name: str, csv_path: Path, field_types: dict[str, str]) -> None:
    """Read CSV and insert records into Airtable table."""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_name}"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    # Read CSV rows
    with open(csv_path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    
    # Convert to Airtable records using dict lookup for type conversion
    records = [
        {
            "fields": {
                key: TYPE_CONVERTERS.get(field_types.get(key, "text"), str)(value)
                for key, value in row.items()
                if value.strip()  # Skip empty values
            }
        }
        for row in rows
    ]
    
    # Insert in batches of 10 (Airtable API limit)
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        response = requests.post(url, headers=headers, json={"records": batch, "typecast": True})
        
        if response.status_code == 200:
            logger.info(f"Inserted batch {i//10 + 1} ({len(batch)} records)")
        else:
            logger.error(f"Failed batch {i//10 + 1}: {response.status_code} - {response.text}")
    
    logger.success(f"Inserted {len(records)} total records into {table_name}")


if __name__ == "__main__":
    logger.info("Creating Airtable tables and inserting data...")
    
    # Create Products table and insert data
    create_table("Products", PRODUCTS_SCHEMA)
    insert_records(
        "Products",
        BASE_DIR / "data/sample/airtable_products.csv",
        {"Unit Price": "currency", "Qty Available": "number", "Active": "checkbox"}
    )
    
    # Create Customers table and insert data
    create_table("Customers", CUSTOMERS_SCHEMA)
    insert_records(
        "Customers",
        BASE_DIR / "data/sample/airtable_customers.csv",
        {"Credit Limit": "currency", "Open AR": "currency"}
    )
    
    logger.success("Done!")
