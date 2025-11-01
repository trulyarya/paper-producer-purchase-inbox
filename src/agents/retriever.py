from typing import Any, Annotated
from pydantic import BaseModel, ConfigDict, Field, computed_field

from agent_framework import ChatAgent, ai_function

from agents.base import chat_client
from aisearch.azure_search_tools import search_products, search_customers


class RetrievedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matched_customer_id: Annotated[
        str,
        Field(
            description="Resolved customer identifier from CRM (Customers) "
            "through similarity search",
        ),
    ]
    matched_customer_name: Annotated[
        str,
        Field(
            description="Resolved customer name from CRM (Customers) "
            "through similarity search",
        ),
    ]
    matched_customer_address: Annotated[
        str,
        Field(
            description="Resolved customer address from CRM (Customers) "
            "through similarity search",
        ),
    ]
    matched_product_sku: Annotated[
        str,
        Field(
            description="Matched product SKU identifier from catalog (Products) "
            "through similarity search",
        ),
    ]
    matched_product_name: Annotated[
        str,
        Field(
            description="Matched product name or title from catalog (Products) "
            "through similarity search",
        ),
    ]
    matched_product_qty_available: Annotated[
        int,
        Field(
            ge=0,
            description="Quantity available in stock for this SKU, from catalog "
            "retrieved from Products table through similarity search",
        ),
    ]
    ordered_qty: Annotated[
        int,
        Field(
            gt=0,
            strict=True,
            description="Quantity ordered by customer for this line item "
            "based on PO email",
        ),
    ]
    price: Annotated[
        float,
        Field(
            ge=0,
            strict=True,
            description="Unit price in EUR",
        ),
    ]
    vat_rate: Annotated[
        float,
        Field(
            default=0.19,
            description="VAT rate (default 19% for Germany)",
        ),
    ]
    
    @computed_field
    @property
    def product_in_stock(self) -> Annotated[
        bool,
        Field(
            description="Whether the item is in stock and available: "
            "only `True` if: `matched_product_qty_available >= ordered_qty` "
            "else: `False`",
        ),
    ]:
        return True if self.matched_product_qty_available >= self.ordered_qty else False
    
    @computed_field
    @property
    def line_item_subtotal(self) -> Annotated[
        float,
        Field(
            description="Line item subtotal for each SKU (ordered_qty * price)",
        ),
    ]:
        return self.ordered_qty * self.price


class RetrievedPO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_id: Annotated[
        str,
        Field(
            description="Gmail message ID of the original purchase order email",
        ),
    ]
    customer_id: Annotated[
        str,
        Field(
            description="Customer identifier or account number",
        ),
    ]
    customer_name: Annotated[
        str,
        Field(
            description="Customer's business or contact name",
        ),
    ]
    customer_open_ar: Annotated[
        float,
        Field(
            description="Customer's current open accounts receivable amount",
        ),
    ]
    customer_credit_limit: Annotated[
        float,
        Field(
            description="Customer's credit limit",
        ),
    ]
    items: Annotated[
        list[
            RetrievedItem
        ],
        Field(
            description="list of retrieved order line items (products) matched "
            "through similarity search",
        ),
    ]

    @computed_field
    @property
    def customer_available_credit(self) -> Annotated[
        float,
        Field(
            description="Customer's available credit to fulfill this order "
            "(customer_credit_limit - customer_open_ar)",
        ),
    ]:
        return self.customer_credit_limit - self.customer_open_ar
    
    @computed_field
    @property
    def tax(self) -> Annotated[
        float,
        Field(
            ge=0,
            strict=True,
            description="Calculated sales tax (sum of line subtotal * VAT rate)",
        ),
    ]:
        return sum(item.line_item_subtotal * item.vat_rate for item in self.items)

    @computed_field
    @property
    def shipping(
        self,
    ) -> Annotated[
        float,
        Field(
            ge=0,
            strict=True,
            description="Flat shipping fee (€25 if subtotal > 0)"
        ),
    ]:
        return 25.0 if self.subtotal > 0 else 0.0

    @computed_field
    @property
    def subtotal(
        self,
    ) -> Annotated[
        float,
        Field(
            ge=0,
            strict=True,
            description="Subtotal of all line items before tax and shipping",
        ),
    ]:
        return sum(item.line_item_subtotal for item in self.items)

    @computed_field
    @property
    def order_total(
        self,
    ) -> Annotated[
        float,
        Field(
            ge=0,
            strict=True,
            description="Final total: subtotal + tax + shipping"
        ),
    ]:
        return self.subtotal + self.tax + self.shipping


retriever = ChatAgent(
    chat_client=chat_client,
    name="retriever",
    instructions=(
        "You're helpful and accurate order retriever sub-agent. "
        "You've been given a ParsedPO JSON representing a parsed purchase order "
        "from a customer PO email, that includes: customer details and line items.\n\n"
        "Your task is to resolve and enrich the ParsedPO using Azure AI search "
        "and the Airtable CRM.\nFor each line item, find the SKU, name, "
        "unit price, and availability using your tools that search Azure AI "
        "(using data from Airtable tables).\n\nResolve or create the customer. "
        "Call check_credit with "
        "the order total you compute from the resolved line subtotals, VAT, "
        "and flat shipping (€25 whenever the subtotal is positive). "
        "Return a RetrievedPO JSON with the customer fields and "
        "resolved items only; tax, shipping, subtotal, and "
        "total are computed automatically. The output must conform to the "
        "defined RetrievedPO schema."
    ),
    tools=[
        search_customers,
        search_products,
    ],
    response_format=RetrievedPO,
)
