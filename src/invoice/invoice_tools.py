"""
Helper for generating invoice PDFs from HTML templates.

This module provides functionality to:
1. Convert HTML invoice files to PDF format using WeasyPrint
2. Upload the generated PDFs to Azure Blob Storage
3. Return publicly accessible URLs for the uploaded invoices

The module uses Azure DefaultAzureCredential for authentication and
requires the following environment variables:
- AZURE_STORAGE_CONNECTION_STRING: Azure Storage account URL
- AZURE_INVOICE_CONTAINER: Container name for saving invoices (default: invoices)
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv
from weasyprint import HTML  # For HTML to PDF conversion
from jinja2 import Environment, FileSystemLoader, select_autoescape  # templating

from azure.core.exceptions import ResourceExistsError  # handles container error
from azure.identity import DefaultAzureCredential  # For Azure authentication
from azure.storage.blob import BlobServiceClient, ContentSettings

load_dotenv()  # Load environment variables from .env file


def _render_invoice_template(template_path: Path, order_context: dict) -> Path:
    """Render HTML invoice template with Jinja2, return the filled file path."""

    env = Environment(
        loader=FileSystemLoader(
            str(template_path.parent)
        ),  # Load HTML template
        autoescape=select_autoescape(enabled_extensions=(
            "html", "xml")
        ),  # Autoescape for security
    )

    # Load the specific template
    template = env.get_template(template_path.name)
    # Render with context, `**` unpacks the dictionary
    rendered = template.render(**order_context)

    output_path = template_path.with_name(
        f"{template_path.stem}_filled.html")  # Output path
    # Write rendered HTML to file
    output_path.write_text(rendered, encoding="utf-8")

    return output_path


def generate_invoice_pdf_url(
    html_template: str | Path,
    order_context: dict,
) -> str:
    """Render HTML invoice template, upload the generated PDF & return its URL.

    This function performs the following steps:
    1. Validates that the template exists
    2. Renders the template with the provided context
    3. Converts the rendered HTML to PDF bytes using WeasyPrint
    4. Connects to Azure Blob Storage using DefaultAzureCredential
    5. Creates the container if it doesn't already exist
    6. Uploads the PDF with a timestamped filename
    7. Returns the public URL of the uploaded PDF

    Args:
        html_template: Path or string pointing to the HTML template file.
        order_context: Dictionary containing data to fill into the template.

    Returns:
        str: URL of the uploaded PDF invoice in Azure Blob Storage.

    Raises:
        FileNotFoundError: If the specified HTML file does not exist.
    """
    template_path = Path(html_template)

    # Verify the HTML template exists before attempting rendering
    if not template_path.exists():
        raise FileNotFoundError(
            f"Invoice HTML file not found: {template_path}")

    rendered_html_path = _render_invoice_template(template_path, order_context)

    # Convert HTML to PDF bytes in memory using WeasyPrint
    pdf_content = HTML(filename=str(rendered_html_path)).write_pdf()

    # Ensure PDF content was generated successfully and is not empty
    if not pdf_content:
        raise ValueError(
            "Failed to generate PDF content from HTML. Cannot upload empty PDF.")

    # Retrieve Azure Storage configuration from environment variables
    storage_account_url = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if storage_account_url is None:
        raise ValueError(
            "AZURE_STORAGE_CONNECTION_STRING environment variable is not set."
        )

    container_name = os.getenv("AZURE_INVOICE_CONTAINER", "invoices")

    # Initialize Azure Blob Service client with managed identity authentication
    blob_service = BlobServiceClient(
        account_url=storage_account_url,
        credential=DefaultAzureCredential(),
    )

    # Generate unique blob name for the PDF invoice
    # Example output: invoice-template-1698249600.pdf
    blob_name = f"{rendered_html_path.stem}-{int(time.time())}.pdf"

    # Get reference to the container client
    container_client = blob_service.get_container_client(container_name)

    # Create container if it doesn't exist (idempotent operation)
    try:
        container_client.create_container()
    except ResourceExistsError:
        pass  # Container already exists, continue with upload

    # Get blob client for the specific PDF file
    blob_client = container_client.get_blob_client(blob_name)

    # Upload PDF bytes to blob storage with proper content type
    # overwrite=True ensures we can re-upload if needed
    blob_client.upload_blob(
        pdf_content,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/pdf"),
    )

    return blob_client.url  # Return the public URL of the uploaded PDF


##################################
### Only for our local testing ###
##################################
if __name__ == "__main__":
    # This block runs only when the module is executed directly (not imported).
    # Simple test case to generate and upload an invoice PDF and print the URL.
    sample_template_path = Path("./src/invoice/invoice_template.html")
    sample_order_context = {
        "invoice": {
            "number": "INV-12345",
            "issue_date": "2025-10-26",
            "due_date": "2025-11-25",
        },
        "customer": {
            "company": "Acme Corp",
            "contact": "Jane Smith",
            "address1": "123 Main St",
            "address2": "New York City, NY 10001",
        },
        "payment": {
            "terms": "Net 30",
            "method": "Bank wire",
            "po_number": "PO-9876",
        },
        "items": [
            {
                "description": "Widget A",
                "qty": 10,
                "unit": "pcs",
                "unit_price": 2.5,
                "line_total": 25.0,
            },
            {
                "description": "Widget B",
                "qty": 5,
                "unit": "pcs",
                "unit_price": 5.0,
                "line_total": 25.0,
            },
        ],
        "totals": {
            "subtotal": 50.0,
            "tax": 9.5,
            "shipping": 15.0,
            "total": 74.5,
        },
    }

    uploaded_invoice_url = generate_invoice_pdf_url(
        html_template=sample_template_path,
        order_context=sample_order_context,
    )

    # URL of the uploaded PDF
    print(f"Uploaded PDF URL: {uploaded_invoice_url}")
