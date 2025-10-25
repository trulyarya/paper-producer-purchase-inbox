"""
Pydantic Schemas for O2C Multi-Agent System

All schemas used by the Order-to-Cash purchase order processing agents.
Organized by workflow stage: Triage → Parser → SKU Resolution → Comms.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import date


# ============================================================================
# 1. EMAIL INBOX TRIAGE AGENT SCHEMAS
# Used by the triage agent to classify incoming emails as PO or non-PO.
# ============================================================================

class TriageResult(BaseModel):
    """Email classification: is it a PO or not?
    Binary decision with confidence score and reasoning."""
    is_po: bool = Field(..., description="True if email is a purchase order")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    reason: str = Field(..., description="Brief classification explanation")
    subject: Optional[str] = Field(None, description="Email subject line")
    sender: Optional[str] = Field(None, description="Email sender address")
    body: Optional[str] = Field(None, description="Email body text")


# ============================================================================
# 2. ORDER STRUCTURING/PO PARSER AGENT SCHEMAS
# Used by the parser agent to extract structured data from PO emails.
# ============================================================================

class CustomerInfo(BaseModel):
    """Customer/buyer information from email.
    Contains company name, contact person, and email address."""
    customer_name: Optional[str] = Field(None, description="Company name")
    contact_person: Optional[str] = Field(None, description="Contact name")
    email: Optional[str] = Field(None, description="Email address")

class OrderLine(BaseModel):
    """Individual line item in a purchase order.
    Represents a single product with quantity, pricing, and optional SKU."""
    line_reference: Optional[str] = Field(None, description="Stable identifier for this line if available")
    product_code: Optional[str] = Field(None, description="Product SKU (e.g., PAPER-A4-100-COATEDGLOSS-M)")
    product_description: str = Field(..., description="Product description from email")
    quantity: int = Field(..., gt=0, description="Quantity ordered")
    unit: Optional[str] = Field(None, description="Unit of measure (ream, box, pallet, case)")
    unit_price: Optional[float] = Field(None, ge=0, description="Price per unit")
    line_total: Optional[float] = Field(None, ge=0, description="Line total")

class PurchaseOrder(BaseModel):
    """Complete purchase order extracted from email.
    Main schema containing customer info, order lines, dates, and metadata."""
    po_number: Optional[str] = Field(None, description="PO number/reference")
    order_date: Optional[date] = Field(None, description="Order date")
    requested_ship_date: Optional[date] = Field(None, description="Requested ship date")
    customer: CustomerInfo = Field(..., description="Customer information")
    order_lines: list[OrderLine] = Field(..., min_length=1, description="Order lines (min 1)")
    net_amount: Optional[float] = Field(None, ge=0, description="Total order amount")
    gmail_message_id: Optional[str] = Field(None, description="Gmail message ID")
    notes: Optional[str] = Field(None, description="Special instructions or notes")


# ============================================================================
# 3. CATALOG MATCHING/SKU RESOLUTION SCHEMAS
# Used to pass vector-search candidates to SKU agent & capture its output.
# ============================================================================

class SkuCandidate(BaseModel):
    """Candidate SKU produced by deterministic search."""
    sku: str = Field(..., description="Catalog SKU identifier")
    title: Optional[str] = Field(None, description="Catalog title or display name")
    description: Optional[str] = Field(None, description="Catalog description snippet")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Vector search similarity 0-1")
    unit: Optional[str] = Field(None, description="Unit of measure from catalog")
    unit_price: Optional[float] = Field(None, ge=0, description="Unit price from catalog")
    qty_available: Optional[int] = Field(None, ge=0, description="Available inventory quantity")

class LineCandidateBundle(BaseModel):
    """Deterministic candidate list for a single order line."""
    line_index: int = Field(..., ge=0, description="Zero-based index of the line in the original order")
    original_line: OrderLine = Field(..., description="Original line information")
    candidates: list[SkuCandidate] = Field(..., min_length=1, description="Candidate SKUs sorted by relevance")

class SkuResolutionPayload(BaseModel):
    """Payload passed from orchestrator to the SKU resolver agent."""
    purchase_order: PurchaseOrder = Field(..., description="The parsed purchase order")
    line_candidates: list[LineCandidateBundle] = Field(..., min_length=1, description="Candidate bundles per line")

class OrderLineEnriched(BaseModel):
    """Order line with matched SKU and pricing from catalog.
    Extends OrderLine with catalog SKU, pricing, and match confidence."""
    product_code: str = Field(..., description="Matched SKU from catalog")
    product_description: str = Field(..., description="Original description from email")
    quantity: int = Field(..., gt=0, description="Quantity ordered")
    unit: str = Field(..., description="Unit of measure from catalog")
    unit_price: float = Field(..., ge=0, description="Unit price from catalog")
    line_total: float = Field(..., ge=0, description="Line total (quantity × unit_price)")
    match_confidence: float = Field(..., ge=0.0, le=1.0, description="Match confidence 0-1")
    match_reason: str = Field(..., description="Why this SKU was selected")
    needs_review: bool = Field(False, description="True if human review advised for this line")

class MatchingSummary(BaseModel):
    """Aggregate SKU matching statistics.
    Provides quality metrics across all order lines for review decisions."""
    total_lines: int = Field(..., ge=0, description="Total order lines")
    matched_lines: int = Field(..., ge=0, description="Successfully matched lines")
    avg_confidence: float = Field(..., ge=0.0, le=1.0, description="Average match confidence")
    needs_review: bool = Field(..., description="True if any line confidence < 0.75")
    
    # --- OPTIONAL BUG PREVENTION ---
    # This validator ensures matched_lines doesn't exceed total_lines which is optional (enforce data integrity)

    # field_validator decorator for matched_lines: defines a validation method for the matched_lines field
    @field_validator('matched_lines')

    # 2nd decorator for class method, so we can access class variables:
    @classmethod # in Pydantic v2, field validators MUST be classmethods so we need both decorators stacked

    def validate_matched_lines(cls, v, info) -> None:  # cls is class, v is value, info has other fields
        """Ensure matched_lines ≤ total_lines."""
        data = info.data  # dictionary of all fields
        if 'total_lines' in data and v > data['total_lines']:
            raise ValueError('matched_lines cannot exceed total_lines')
        return v

class OrderTotals(BaseModel):
    """Calculated order totals.
    Contains subtotal, tax, shipping, and grand total amounts."""
    subtotal: float = Field(..., ge=0, description="Sum of all line totals")
    tax: float = Field(..., ge=0, description="Tax amount")
    shipping: float = Field(..., ge=0, description="Shipping cost")
    total: float = Field(..., ge=0, description="Grand total")

class CreditCheckResult(BaseModel):
    """Credit check result for order approval.
    Contains approval status, credit limits, and reasoning."""
    approved: bool = Field(..., description="True if order approved")
    credit_limit: float = Field(..., ge=0, description="Customer credit limit")
    open_ar: float = Field(..., ge=0, description="Current open accounts receivable")
    available_credit: float = Field(..., ge=0, description="Available credit remaining")
    reason: Optional[str] = Field(None, description="Explanation if not approved")

class EnrichedPurchaseOrder(BaseModel):
    """Purchase order with matched SKUs, pricing, and downstream context.
    Complete PO with all lines enriched, matching summary statistics, and optional
    financial/credit metadata required for communications and fulfillment."""
    po_number: Optional[str] = Field(None, description="Reference to the original PO number if available")
    customer: Optional[CustomerInfo] = Field(None, description="Customer details carried over from the parser")
    order_lines: list[OrderLineEnriched] = Field(..., min_length=1, description="Enriched order lines")
    matching_summary: MatchingSummary = Field(..., description="Matching statistics")
    totals: Optional[OrderTotals] = Field(None, description="Calculated order totals provided by the catalog agent")
    credit_result: Optional[CreditCheckResult] = Field(None, description="Credit decision associated with this order")
    gmail_message_id: Optional[str] = Field(None, description="Original Gmail message/thread id for downstream replies")


# ============================================================================
# 4. FULFILLMENT VALIDATION SCHEMAS
# Used by fulfillment validator to determine order routing (success vs exception path).
# ============================================================================

class CustomerValidationStatus(BaseModel):
    """Customer lookup/creation validation result."""
    customer_id: str = Field(..., description="Airtable customer record ID")
    matched: bool = Field(..., description="True if existing customer was found (not created)")
    credit_limit: float = Field(..., ge=0, description="Customer credit limit")
    open_ar: float = Field(..., ge=0, description="Current open accounts receivable")
    is_new: bool = Field(..., description="True if customer was newly created")
    customer_name: str = Field(..., description="Customer name")

class InventoryValidationStatus(BaseModel):
    """Inventory availability check result for a single SKU."""
    sku: str = Field(..., description="Product SKU checked")
    requested: int = Field(..., gt=0, description="Requested quantity")
    available: int = Field(..., ge=0, description="Available inventory quantity")
    in_stock: bool = Field(..., description="True if sufficient stock available")

class FulfillabilityResult(BaseModel):
    """Result of fulfillment validation check.
    Determines whether order can be fulfilled and routes to appropriate handler."""
    is_fulfillable: bool = Field(..., description="True if order can be completely fulfilled")
    blocking_reasons: list[str] = Field(
        default_factory=list, 
        description="Reasons preventing fulfillment (CREDIT_EXCEEDED, PRODUCT_NOT_FOUND, OUT_OF_STOCK)"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking concerns that should be noted"
    )
    customer_status: CustomerValidationStatus = Field(
        ..., 
        description="Customer lookup/creation result with credit info"
    )
    inventory_status: list[InventoryValidationStatus] = Field(
        default_factory=list,
        description="Inventory check results for each line item"
    )


# ============================================================================
# 5. COMMS & EXCEPTIONS AGENT 
# Does NOT require new schemas beyond those defined above.
# ============================================================================