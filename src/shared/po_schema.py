"""
Pydantic schemas for purchase order extraction from email.
Designed to align with existing CRM structure (orders, order lines, customers).
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class OrderLine(BaseModel):
    """Individual line item in a purchase order."""
    product_code: Optional[str] = Field(None, description="Product SKU/code (e.g., PAPER-A4-100-COATEDGLOSS-M)")
    product_description: str = Field(..., description="Human-readable product description from email")
    quantity: int = Field(..., description="Quantity ordered")
    unit: Optional[str] = Field(None, description="Unit of measure (e.g., ream, box, pallet)")
    unit_price: Optional[float] = Field(None, description="Price per unit if mentioned")
    line_total: Optional[float] = Field(None, description="Total for this line if mentioned")
    
    
class CustomerInfo(BaseModel):
    """Customer information extracted from email."""
    customer_name: Optional[str] = Field(None, description="Company name of the buyer")
    contact_person: Optional[str] = Field(None, description="Name of person placing order")
    email: Optional[str] = Field(None, description="Email address of sender")
    

# The final Purchase Order Schema to extract from email
class PurchaseOrder(BaseModel):
    """Complete purchase order extracted from email."""
    po_number: Optional[str] = Field(None, description="Purchase order number/reference")
    order_date: Optional[date] = Field(None, description="Date order was placed")
    requested_ship_date: Optional[date] = Field(None, description="Requested delivery/shipment date")
    customer: CustomerInfo = Field(..., description="Customer/buyer information")
    order_lines: list[OrderLine] = Field(..., description="List of items ordered", min_length=1)
    net_amount: Optional[float] = Field(None, description="Total order amount if mentioned")
    gmail_message_id: Optional[str] = Field(None, description="Gmail message ID for reference")
    notes: Optional[str] = Field(None, description="Any special instructions or notes")


#---------------------------------------------


# Define the response format for PO triage
class POTriageResult(BaseModel):
    """Determines if an email is a purchase order or not."""
    is_po: bool = Field(..., description="True if the email is a purchase order, False otherwise")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score between 0 and 1")
    reason: str = Field(..., description="Very brief explanation for the classification decision")