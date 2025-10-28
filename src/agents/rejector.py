from typing import Annotated

from agent_framework import ChatAgent
from pydantic import BaseModel, ConfigDict, Field

from agents.base import chat_client
from agents.fulfiller import send_slack_notification


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
        "Send the reply via respond_unfulfillable_email(). Optionally notify the ops team via Slack. "
        "Return RejectResult with ok=true when done."
    ),
    tools=[
        # respond_unfulfillable_email,
        send_slack_notification
    ],
    response_format=RejectResult,
)
