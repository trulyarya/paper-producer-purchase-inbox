from typing import Annotated

from agent_framework import ChatAgent
from pydantic import BaseModel, ConfigDict, Field

from agents.base import chat_client


class ProductLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_sku: Annotated[
        str,
        Field(
            description="Line item product-SKU or identifier from customer's PO email"
        ),
    ]
    product_name: Annotated[
        str,
        Field(
            description="Line item product name or description from customer's PO email"
        ),
    ]
    ordered_qty: Annotated[
        int,
        Field(
            gt=0,
            strict=True,
            description="Quantity requested for the line item from PO",
        ),
    ]


class ParsedPO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_id: Annotated[
        str, Field(description="ID of the email this parsed purchase order came from")
    ]
    customer_email: Annotated[
        str,
        Field(
            description="Customer email address where the PO email was sent from, extracted"
        ),
    ]
    customer_company_name: Annotated[
        str, Field(description="Customer or company name extracted from the PO email")
    ]
    customer_billing_address: Annotated[
        str,
        Field(
            description="Billing address extracted for the customer from the PO email"
        ),
    ]
    customer_shipping_address: Annotated[
        str,
        Field(
            description="Shipping address extracted for the customer from the PO email"
        ),
    ]
    line_items: Annotated[
        list[ProductLineItem],
        Field(
            description="List of individual line items parsed from the purchase order email"
        ),
    ]


parser = ChatAgent(
    chat_client=chat_client,
    name="parser",
    instructions=(
        "Parse the email selected by the classifier into structured purchase "
        "order fields. Only use the `email` object from the classifier's latest "
        "response object as your source material. "
        "Return a ParsedPO JSON that matches the provided response schema, "
        "inferring reasonable defaults as needed."
    ),
    tools=[
        # clean_email_payload
    ],
    response_format=ParsedPO,
)
