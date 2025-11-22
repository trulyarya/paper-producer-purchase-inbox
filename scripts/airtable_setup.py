"""
Airtable workspace automation: creates base, tables, uploads CSV data.
If AIRTABLE_API_KEY or AIRTABLE_WORKSPACE_ID are missing, prompts for them
and saves to .env (minimal interactive flow similar to slack_setup).
"""

import os
import csv
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv, set_key
from loguru import logger

load_dotenv()  # Load any existing .env values early

API_KEY = os.getenv("AIRTABLE_API_KEY")
WORKSPACE_ID = os.getenv("AIRTABLE_WORKSPACE_ID")  # Workspace URL contains id e.g. https://airtable.com/workspaces/<wspsXXXXXXXXXXXX>

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"
PRODUCTS_CSV_FILE = BASE_DIR / "data/sample/airtable_products.csv"
CUSTOMERS_CSV_FILE = BASE_DIR / "data/sample/airtable_customers.csv"

# Table schemas
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


def create_base(workspace_id: str, base_name: str = "PaperCo O2C Demo") -> str:
    """Create a new Airtable base with tables and return its ID."""
    url = "https://api.airtable.com/v0/meta/bases"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    # Airtable requires at least one table with one field in the create request
    data = {
        "name": base_name,
        "workspaceId": workspace_id,
        "tables": [
            {"name": "Products", "fields": PRODUCTS_SCHEMA},
            {"name": "Customers", "fields": CUSTOMERS_SCHEMA}
        ]
    }
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        new_base_id = response.json()["id"]
        logger.success(f"Created base '{base_name}': {new_base_id}")
        return new_base_id
    
    logger.error(f"Failed to create base: {response.status_code} - {response.text}")
    sys.exit(1)


def create_table(base_id: str, table_name: str, fields: list[dict]) -> None:
    """Create a table in the base."""
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    response = requests.post(url, headers=headers, json={"name": table_name, "fields": fields})
    
    if response.status_code == 200:
        logger.success(f"Created table: {table_name}")
    else:
        logger.warning(f"Failed to create {table_name}: {response.status_code} - {response.text}")


def upload_csv(base_id: str, table_name: str, csv_path: Path) -> None:
    """Upload CSV records to Airtable table in batches."""
    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    with open(csv_path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    
    records = [{"fields": {k: v for k, v in row.items() if v.strip()}} for row in rows]
    
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        response = requests.post(url, headers=headers, json={"records": batch, "typecast": True})
        
        if response.status_code == 200:
            logger.info(f"Uploaded batch {i//10 + 1} ({len(batch)} records)")
        else:
            logger.error(f"Failed batch {i//10 + 1}: {response.status_code} - {response.text}")
    
    logger.success(f"Uploaded {len(records)} records to {table_name}")


def airtable_setup_flow() -> dict:
    """Interactive Airtable setup: prompts for credentials, creates base, uploads data."""
    global API_KEY, WORKSPACE_ID # 'global' is needed to modify these variables.
    
    if not API_KEY:
        logger.info(
            "AIRTABLE_API_KEY missing in `.env`. Create one at https://airtable.com/create/tokens")
        logger.info(
            "(Give it scopes: 'data.records:read/write', 'schema.bases:read/write')\n")
        
        API_KEY = input("Paste Airtable API key: ").strip()

        while len(API_KEY) < 15:
            logger.error("API key empty or incomplete. Please try again.\n")
            
            API_KEY = input(
                "Paste a valid Airtable API key: "
            ).strip()

        # Save the Airtable API key to .env
        set_key(ENV_FILE, "AIRTABLE_API_KEY", API_KEY)
        
        logger.success("Saved API key to AIRTABLE_API_KEY in `.env`.")
    else:
        logger.warning(
            "An existing AIRTABLE_API_KEY found in `.env` and will be re-used. "
            "If you want to use a different key, replace it in the `.env` file manually.")


    if not WORKSPACE_ID:
        logger.info("AIRTABLE_WORKSPACE_ID missing in `.env`. Find it in workspace URL:")
        logger.info("https://airtable.com/workspaces/<wspsID>")
        
        WORKSPACE_ID = input("Paste workspace ID (starts with 'wsps'): ").strip()
        
        while not WORKSPACE_ID.startswith("wsps") or (len(WORKSPACE_ID) < 10):
            logger.error("Invalid workspace ID. Please try again.\n")
            
            WORKSPACE_ID = input(
                "Paste a valid workspace ID (starts with 'wsps'): "
            ).strip()
        
        set_key(ENV_FILE, "AIRTABLE_WORKSPACE_ID", WORKSPACE_ID)
        
        logger.success("Saved workspace ID to AIRTABLE_WORKSPACE_ID in `.env`!")
    else:
        logger.warning(
            "An existing AIRTABLE_WORKSPACE_ID found in `.env` and will be re-used. "
            "If you want to use a different workspace, replace it in the `.env` file manually.")
        
    logger.info(f"Creating base in workspace {WORKSPACE_ID}...")
    
    base_id = create_base(WORKSPACE_ID)
    set_key(ENV_FILE, "AIRTABLE_BASE_ID", base_id)

    logger.success("Saved AIRTABLE_BASE_ID in `.env`.")
    logger.info("Uploading CSV data...")
    
    upload_csv(base_id, "Products", PRODUCTS_CSV_FILE)
    upload_csv(base_id, "Customers", CUSTOMERS_CSV_FILE)
    
    logger.success("Airtable setup complete!")
    
    return {
        "AIRTABLE_API_KEY": API_KEY,
        "AIRTABLE_WORKSPACE_ID": WORKSPACE_ID,
        "AIRTABLE_BASE_ID": base_id,
    }


if __name__ == "__main__":
    airtable_setup_flow()
