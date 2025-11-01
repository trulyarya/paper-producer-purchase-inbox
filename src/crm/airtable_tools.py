"""
Airtable CRM Tools - Data Sync and Write Operations
Handles Airtable API for: sync jobs, customer creation, direct lookups.
Resolver agent uses Azure AI Search for reads, not this module.
"""

import os
from datetime import datetime
import requests
from typing import Any
from dotenv import load_dotenv
from sqlalchemy import all_

# ============================================================================
# ENVIRONMENT CONFIGURATION
# ============================================================================

load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")  # Personal access token
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")  # Base identifier
AIRTABLE_PRODUCTS_TABLE = os.getenv("AIRTABLE_PRODUCTS_TABLE", "Products")
AIRTABLE_CUSTOMERS_TABLE = os.getenv("AIRTABLE_CUSTOMERS_TABLE", "Customers")
AIRTABLE_API_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
AIRTABLE_API_HEADER = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}


# ============================================================================
# AIRTABLE API HELPER FUNCTIONS
# ============================================================================


def _fetch_all_records(table_name: str) -> list[dict[str, Any]]:
    """
    Fetches all records from specified Airtable table.
    Handles pagination automatically for large datasets.

    Args:
        table_name: Name of the Airtable table to query
    Returns:
        list of record dictionaries with fields data
    """
    url = f"{AIRTABLE_API_URL}/{table_name}"  # Table endpoint
    all_records = []  # Accumulator for all pages
    offset = None  # Pagination cursor

    while True:  # Loop until all pages are fetched
        # Add offset if present to get next page
        params = {"offset": offset} if offset else {}

        response = requests.get(
            url,
            headers=AIRTABLE_API_HEADER,
            params=params
        )  # API call to FETCH records

        response.raise_for_status()  # Raise on 4xx/5xx errors

        data = response.json()  # Parse JSON response
        all_records.extend(data.get("records", []))  # Append current page

        offset = data.get("offset")  # Get next page cursor
        if not offset:  # No more pages
            break

    return all_records


def _create_record(
        table_name: str,
        fields: dict[str, Any]
) -> dict[str, Any]:
    """
    Creates a new record in specified Airtable table.
    
    Args:
        table_name: Name of the Airtable table to create record in
        fields: Dictionary of field names and values for the new record
    Returns:
        Created record with ID and fields
    """
    url = f"{AIRTABLE_API_URL}/{table_name}"  # Table endpoint
    payload = {"fields": fields}  # Wrap fields in Airtable format

    response = requests.post(
        url,
        headers=AIRTABLE_API_HEADER,
        json=payload
    )  # API call to CREATE record

    response.raise_for_status()  # Raise on 4xx/5xx errors

    return response.json()  # Return created record


def _update_record(
        table_name: str,
        record_id: str,
        fields: dict[str, Any]
) -> dict[str, Any]:
    """
    Updates an existing record in specified Airtable table.
    
    Args:
        table_name: Name of the Airtable table containing the record
        record_id: ID of the record to update 
        fields: Dictionary of field names and new values for the record
    Returns:
        Updated record with ID and fields
    """
    url = f"{AIRTABLE_API_URL}/{table_name}/{record_id}"  # Record endpoint
    payload = {"fields": fields}  # Wrap fields in Airtable format

    response = requests.patch(
        url,
        headers=AIRTABLE_API_HEADER,
        json=payload
    )  # API call to UPDATE record

    response.raise_for_status()  # Raise on 4xx/5xx errors

    return response.json()  # Return updated record

# ===================================================================
# DATA SYNC FUNCTIONS (for easy Azure AI Search ingestion): fetch all
# ===================================================================

def get_all_products() -> list[dict[str, Any]]:
    """Fetches all products for AI Search sync. Returns raw Airtable records."""
    return _fetch_all_records(AIRTABLE_PRODUCTS_TABLE)


def get_all_customers() -> list[dict[str, Any]]:
    """Fetches all customers for AI Search sync. Returns raw Airtable records"""
    return _fetch_all_records(AIRTABLE_CUSTOMERS_TABLE)


# ============================================================================
# WRITE OPERATIONS (create new records)
# ============================================================================

def add_new_customer(
        customer_name: str,
        customer_email: str,
        customer_address: str,
) -> None:
    """Creates new customer in Airtable when not found in AI Search in Airtable.
    
    Args:
        customer_name: Full name of the customer
        customer_email: Email address of the customer
        customer_address: Billing/shipping address of the customer
    Returns:
        None
    """

    all_customers = _fetch_all_records(AIRTABLE_CUSTOMERS_TABLE)
    # columns: Customer ID, Name, Email, Billing Address, Shipping Address,
    #          Credit Limit, Open AR, Currency, Status

    max_id = 5000  # Start from C-5001

    for customer in all_customers:  # Find max existing Customer ID
        cust_id = customer["fields"].get("Customer ID", "C-5000")
        id_num = int(cust_id.split("-")[1])
        max_id = max(max_id, id_num)

    new_id = f"C-{max_id + 1}"  # New Customer ID

    fields = {  # Prepare fields for new record
        "Customer ID": new_id,
        "Name": customer_name,
        "Email": customer_email,
        "Billing Address": customer_address,
        "Credit Limit": 3000.0,  # Initial credit limit
        "Open AR": 0.0,
        "Currency": "EUR",
        "Status": "Active"
    }

    _create_record(AIRTABLE_CUSTOMERS_TABLE, fields)


def update_inventory(
        ordered_qty: int,
        product_sku: str,
) -> None:
    """Updates customer's inventory and backorder in Airtable.

    Args:
        ordered_qty: Quantity of product ordered
        product_sku: SKU of the product to update
    """
    all_products = _fetch_all_records(AIRTABLE_PRODUCTS_TABLE)
    # columns: SKU, Title, Description, UOM, Unit Price, Qty Available,
    #          Active, Attributes JSON, Last Updated

    record_id: str = ""  # Initialize record_id
    new_inventory: int = 0  # Initialize new_inventory
    
    for product in all_products:
        if product["fields"].get("SKU") == product_sku:
            record_id = product["id"]  # Capture the Airtable record ID
            # Deduct ordered qty from stock
            new_inventory: int = product["fields"].get(
                "Qty Available",
                0
            ) - ordered_qty
        else:
            raise ValueError(
                f"Product with SKU '{product_sku}' not found in Airtable"
            )

    fields = {
        "Qty Available": new_inventory,
        "Last Updated": datetime.now().isoformat(),
    }

    _update_record(AIRTABLE_PRODUCTS_TABLE, record_id, fields)


def update_customer_credit(
        customer_id: str,
        order_amount: float,
) -> float:
    """Updates customer's open accounts receivable (AR) in Airtable.

    Args:
        customer_id: Customer ID to update (e.g., "C-5001")
        new_open_ar: New open AR amount to set
    Returns:
        updated_available_credit: float
    """
    all_customers = _fetch_all_records(AIRTABLE_CUSTOMERS_TABLE)
    # columns: Customer ID, Name, Email, Billing Address, Shipping Address,
    #          Credit Limit, Open AR, Currency, Status

    updated_available_credit = 0.  # Initialize available credit

    for customer in all_customers:
        if customer["fields"].get("Customer ID") == customer_id:
            order_amount = customer["fields"].get("Open AR", 0.0) + order_amount
            updated_available_credit: float = customer["fields"].get(
                "Credit Limit",
                0.0
            ) - order_amount
        else:
            raise ValueError(
                f"Customer with ID '{customer_id}' not found in Airtable"
            )

    fields = {
        "Open AR": order_amount,
    }

    # First, update Open AR field in the record of the customer
    _update_record(AIRTABLE_CUSTOMERS_TABLE, customer_id, fields)

    # Then, return updated available credit which is `credit limit - open AR`
    return updated_available_credit



# ============================================================================
# DIRECT LOOKUP FUNCTIONS (rarely used - prefer AI Search)
# ============================================================================

# def get_product_by_sku(sku: str) -> Optional[dict[str, Any]]:
#     """Direct Airtable lookup by SKU. Use only for validation, not search."""
#     url = f"{AIRTABLE_API_URL}/{AIRTABLE_PRODUCTS_TABLE}"
#     params = {"filterByFormula": f"{{SKU}}='{sku}'"}
#     response = requests.get(url, headers=_get_headers(), params=params)
#     response.raise_for_status()
#     records = response.json().get("records", [])
#     return records[0] if records else None


# def get_customer_by_id(customer_id: str) -> Optional[dict[str, Any]]:
#     """Direct Airtable lookup by customer ID. Use only for validation, not search."""
#     url = f"{AIRTABLE_API_URL}/{AIRTABLE_CUSTOMERS_TABLE}"
#     params = {"filterByFormula": f"{{'Customer ID'}}='{customer_id}'"}
#     response = requests.get(url, headers=_get_headers(), params=params)
#     response.raise_for_status()
#     records = response.json().get("records", [])
#     return records[0] if records else None
