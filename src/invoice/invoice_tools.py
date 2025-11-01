"""Generate invoice PDFs and upload them to Azure Blob Storage."""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

load_dotenv()


def _render_invoice_html(template_path: Path, order_context: dict) -> str:
    """Render the invoice HTML from a Jinja2 template and order context.
    Args:
        template_path: Path to the HTML template file
        order_context: Context dictionary for rendering the template
    Returns:
        The rendered HTML as a string."""

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    )
    return env.get_template(template_path.name).render(**order_context)


def _html_to_pdf_bytes(html_content: str, base_path: Path) -> bytes:
    pdf_content = HTML(string=html_content, base_url=base_path.as_uri()).write_pdf()
    if not pdf_content:
        raise ValueError("Failed to generate PDF content from HTML.")
    return pdf_content


def generate_invoice_pdf_url(
    html_template: str | Path,
    order_context: dict,
) -> str:
    """Generate an invoice PDF from an HTML template and upload it to Azure Blob Storage.
    Args:
        html_template: Path to the HTML template file
        order_context: Context dictionary for rendering the template
    Returns:
        URL of the uploaded PDF in Azure Blob Storage
    Raises:
        FileNotFoundError: If the HTML template file does not exist
        ValueError: If PDF generation fails or environment variables are not set
    """

    template_path = Path(html_template)

    if not template_path.exists():
        raise FileNotFoundError(f"Invoice HTML file not found: {template_path}")

    html_content = _render_invoice_html(template_path, order_context)
    pdf_content = _html_to_pdf_bytes(html_content, template_path.parent.resolve())

    storage_account_url = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if storage_account_url is None:
        raise ValueError(
            "AZURE_STORAGE_CONNECTION_STRING environment variable is not set."
        )

    container_name = os.getenv("AZURE_INVOICE_CONTAINER", "invoices")

    blob_service = BlobServiceClient(
        account_url=storage_account_url,
        credential=DefaultAzureCredential(),
    )

    blob_name = f"{template_path.stem}-{int(time.time())}.pdf"
    container_client = blob_service.get_container_client(container_name)

    try:
        container_client.create_container()
    except ResourceExistsError:
        pass

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        pdf_content,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/pdf"),
    )

    return blob_client.url


# LOCAL TESTING
if __name__ == "__main__":
    sample_template_path = (
        Path(__file__).parent.parent / "invoice" / "invoice_template.html"
    )
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

    url = generate_invoice_pdf_url(sample_template_path, sample_order_context)
    print(f"Uploaded PDF URL: {url}")
