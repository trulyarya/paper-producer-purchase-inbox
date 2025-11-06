from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_framework import ChatAgent, ai_function

from agents.base import chat_client
from aisearch.azure_search_tools import search_products, search_customers


class RetrievedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: Annotated[
        str,
        Field(
            description="Resolved customer identifier from CRM (Customers) "
            "through similarity search",
        ),
    ]
    customer_name: Annotated[
        str,
        Field(
            description="Resolved customer name from CRM (Customers) "
            "through similarity search",
        ),
    ]
    customer_address: Annotated[
        str,
        Field(
            description="Resolved customer address from CRM (Customers) "
            "through similarity search",
        ),
    ]
    product_sku: Annotated[
        str,
        Field(
            description="Matched product SKU identifier from catalog (Products) "
            "through similarity search",
        ),
    ]
    product_name: Annotated[
        str,
        Field(
            description="Matched product name or title from catalog (Products) "
            "through similarity search",
        ),
    ]
    product_qty_available: Annotated[
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
    unit_price: Annotated[
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
    product_in_stock: Annotated[
        bool,
        Field(
            default=False,
            description="Whether the item is in stock and available: "
            "only `True` if: `product_qty_available >= ordered_qty` "
            "else: `False`",
        ),
    ]
    subtotal: Annotated[
        float,
        Field(
            default=0.0,
            ge=0,
            strict=True,
            description="Line item subtotal for each SKU (ordered_qty * unit_price)",
        ),
    ]

    # Compute derived fields after initialization, otherwise the retriever agent may
    # miss including them in the output, if we use computed_field decorators.
    @model_validator(mode="after")  # "after" means this runs after the model has been created
    def _set_computed_fields(self) -> "RetrievedItem":
        self.product_in_stock = self.product_qty_available >= self.ordered_qty
        self.subtotal = self.ordered_qty * self.unit_price
        return self


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
    customer_overall_credit_limit: Annotated[
        float,
        Field(
            description="Customer's overall credit limit",
        ),
    ]
    customer_open_ar: Annotated[
        float,
        Field(
            description="Customer's current open accounts receivable amount " \
            "(how much the customer currently owes)",
        ),
    ]
    customer_available_credit: Annotated[
        float,
        Field(
            default=0.0,
            description="Customer's available credit to fulfill this order "
            "(customer_overall_credit_limit - customer_open_ar)",
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
    tax: Annotated[
        float,
        Field(
            default=0.0,
            ge=0,
            strict=True,
            description="Calculated sales tax (sum of line subtotal * VAT rate)",
        ),
    ]
    shipping: Annotated[
        float,
        Field(
            default=0.0,
            ge=0,
            strict=True,
            description="Flat shipping fee (€25 if subtotal > 0)",
        ),
    ]
    subtotal: Annotated[
        float,
        Field(
            default=0.0,
            ge=0,
            strict=True,
            description="Subtotal of all line items before tax and shipping",
        ),
    ]
    order_total: Annotated[
        float,
        Field(
            default=0.0,
            ge=0,
            strict=True,
            description="Final total: subtotal + tax + shipping",
        ),
    ]
    customer_can_order_with_credit: Annotated[
        bool,
        Field(
            description="Whether the customer can place orders using credit: "
            "Only 'True' if customer_available_credit >= order_total else 'False'",
        ),
    ]


    # Compute derived fields after initialization, otherwise the retriever agent may
    # miss including them in the output, if we use computed_field decorators.
    @model_validator(mode="after")  # "after" means this runs after the model has been created
    def _set_totals(self) -> "RetrievedPO":
        self.customer_available_credit = self.customer_overall_credit_limit - self.customer_open_ar
        self.tax = sum(item.subtotal * item.vat_rate for item in self.items)
        self.shipping = 25.0 if sum(item.subtotal for item in self.items) > 0 else 0.0
        self.subtotal = sum(item.subtotal for item in self.items)
        self.order_total = self.subtotal + self.tax + self.shipping
        self.customer_can_order_with_credit = self.customer_available_credit >= self.order_total
        return self


retriever = ChatAgent(
    chat_client=chat_client,
    name="retriever",
    instructions=(
        "You are an order enrichment specialist. Given a ParsedPO containing customer details and line items, "
        "your job is to resolve and enrich the data using Azure AI Search tools.\n\n"
        "Process flow:\n"
        "1. For the customer: Call search_customers() with the customer company name, email, and address details "
        "from ParsedPO. Select the best match and extract: customerId, companyName, creditLimit, openAR, and addresses.\n\n"
        "2. For each line item: Call search_products() with the product SKU and name (title or description) from the ParsedPO. "
        "Select the best match for each product item and extract: sku, title, unitPrice, qtyAvailable.\n\n"
        "3. Build the RetrievedPO output object with the exact schema requested as response_format. "
        "Populate all required fields with the enriched data.\n\n"
        "Important: Do not calculate totals manually. The schema has @computed_field properties that automatically "
        "calculate all necessary fields. By providing the required fields, computed fields are derived automatically.\n\n"
        "If a customer match isn't found (new customer), use placeholder values (e.g., customerId='NEW', creditLimit=0, openAR=0) "
        "so the decider agent can handle appropriately."
    ),
    tools=[
        search_customers,
        search_products,
    ],
    response_format=RetrievedPO,
)
