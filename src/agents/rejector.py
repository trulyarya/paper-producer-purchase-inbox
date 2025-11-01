"""Rejector agent configuration.

For now, Slack notifications are sent only for fulfilled orders (via the fulfiller).
This agent does not notify Slack. It will be extended later if needed.
"""

from typing import Annotated

from agent_framework import ChatAgent
from pydantic import BaseModel, ConfigDict, Field

from agents.base import chat_client

from emailing.gmail_tools import respond_unfulfillable_email



class RejectResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rejection_messaging_complete: Annotated[
        bool,
        Field(
            description="Whether the rejection was handled successfully"
        )
    ]


rejector = ChatAgent(
    chat_client=chat_client,
    name="rejector",
    instructions=(
        "The order cannot be fulfilled. Compose a clear, professional "
        "email reply explaining why (e.g. credit issues, unavailable items, etc.) "
        "and what the customer should do next. "
        "Send the reply via respond_unfulfillable_email().\n\n"
        "Return RejectResult with rejection_messaging_complete=true when done."
    ),
    tools=[
        respond_unfulfillable_email,
        # (no Slack notifications for rejections)
    ],
    response_format=RejectResult,
)
