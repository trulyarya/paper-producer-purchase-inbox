from typing import Annotated

from agent_framework import ChatAgent
from pydantic import BaseModel, ConfigDict, Field

from agents.base import chat_client
"""Rejector agent configuration.

Slack notifications are sent only for fulfilled orders (via the fulfiller).
This agent does not notify Slack.
"""


class RejectResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: Annotated[bool, Field(
        description="Whether the rejection was handled successfully")]


rejector = ChatAgent(
    chat_client=chat_client,
    name="rejector",
    instructions=(
        "The order cannot be fulfilled. Compose a clear, professional email reply explaining why "
        "(credit issues, unavailable items, etc.) and what the customer should do next. "
        "Send the reply via respond_unfulfillable_email(). Do not send Slack notifications. "
        "Return RejectResult with ok=true when done."
    ),
    tools=[
        # respond_unfulfillable_email,
        # (no Slack notifications for rejections)
    ],
    response_format=RejectResult,
)
