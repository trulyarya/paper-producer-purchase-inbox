from typing import Annotated, Literal

from agent_framework import ChatAgent
from pydantic import BaseModel, Field

from agents.base import chat_client
from agents.resolver import ResolvedPO


class Decision(BaseModel):
    status: Annotated[Literal["FULFILLABLE", "UNFULFILLABLE"],
                      Field(description="Whether the order can be fulfilled")]
    reason: Annotated[str, Field(
        description="Explanation for the fulfillment decision")]
    payload: Annotated[ResolvedPO, Field(
        description="The original ResolvedPO being evaluated")]


decider = ChatAgent(
    chat_client=chat_client,
    name="decider",
    instructions=(
        "Given a ResolvedPO, decide if it is fulfillable. "
        "If any item is unavailable or credit is insufficient, mark UNFULFILLABLE and set reason. "
        "Otherwise mark FULFILLABLE. "
        "Return a Decision JSON that matches the schema."
    ),
    tools=[],
    response_format=Decision,
)
