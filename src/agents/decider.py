from typing import Annotated, Literal

from agent_framework import ChatAgent
from pydantic import BaseModel, Field

from agents.base import chat_client
from agents.retriever import RetrievedPO


class Decision(BaseModel):
    status: Annotated[
        Literal[
            "FULFILLABLE",
            "UNFULFILLABLE"
        ],
        Field(
            description="Whether the order can be fulfilled or not"
        )
    ]
    reason: Annotated[
        str,
        Field(
            description="Explanation for the final fulfillment decision"
        )
    ]
    input_payload: Annotated[
        RetrievedPO,
        Field(
            description="The original input RetrievedPO that is being evaluated"
        )
    ]


decider = ChatAgent(
    chat_client=chat_client,
    name="decider",
    instructions=(
        "Given the RetrievedPO, decide if the order is fulfillable. "
        "If any item is unavailable, or credit is insufficient "
        "(where customer_available_credit < 0), mark order as UNFULFILLABLE "
        "and set the reason. Otherwise mark order as FULFILLABLE. "
        "Return a Decision JSON that matches the Decision schema."
    ),
    tools=[],
    response_format=Decision,
)
