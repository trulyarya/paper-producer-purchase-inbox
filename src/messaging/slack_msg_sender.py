import os  # Access Slack webhook configuration
from typing import Mapping, Sequence  # Type hints for incoming payloads

import requests  # HTTP client used to invoke the Slack webhook
from dotenv import load_dotenv  # Support loading secrets from a .env file

load_dotenv()  # Make sure environment variables are available at import time


# ----------------------- Slack Message Sender --------------------------

def post_slack_message(
    *,
    fields: Mapping[str, str],  # Summary fields shown in the Slack card
    order_items: Sequence[str],  # Line items to display as a bullet list
    processed_seconds: float | None = None,  # Optional processing duration metric
    notification_email: str | None = None,  # Optional email recipient for context
    agent_name: str | None = None,  # Optional automation agent attribution
    invoice_url: str | None = None,  # Optional link to the generated invoice
    order_url: str | None = None,  # Optional link to the order record
) -> None:
    
    """Post a Slack Block Kit message populated with the supplied order data.
    Args:
        fields: Key/value pairs summarizing the order (e.g., Order ID, Customer).
        order_items: List of item descriptions included in the order.
        processed_seconds: Optional duration taken to process the order.
        notification_email: Optional email address that received the order notification.
        agent_name: Optional name of the automation agent that processed the order.
        invoice_url: Optional URL linking to the generated invoice document.
        order_url: Optional URL linking to the order management record.
        slack_webhook_url: Optional override for the Slack webhook URL.
    Raises:
        ValueError: If required parameters are missing or invalid.
    """
    
    # ----------------------------------------------------------------------
    # -------------------- Validate required parameters --------------------
    # ----------------------------------------------------------------------
    if not fields:
        raise ValueError("fields must contain at least one entry.")  # Guard against missing summary content
    if not order_items:
        raise ValueError("order_items must contain at least one entry.")  # Guard against empty item list

    field_blocks = [
        {"type": "mrkdwn", "text": f"*{label}:*\n{value}"}  # Render each key/value pair as a Slack field
        for label, value in fields.items()
    ]

    order_items_text = "\n".join(f"• {item}" for item in order_items)  # Format items as Slack-friendly bullets


    # ----------------------------------------------------------------------
    # --------------- Build optional context and action blocks -------------
    # ----------------------------------------------------------------------

    context_parts: list[str] = []  # Collect optional context statements
   
    if processed_seconds is not None:
        context_parts.append(f"⏱️ Processed in {processed_seconds:.1f} seconds")  # Surface processing latency
   
    if notification_email:
        context_parts.append(f"📧 Email sent to {notification_email}")  # Note who received the outbound email
   
    if agent_name:
        context_parts.append(f"🤖 Agent: {agent_name}")  # Credit the automation agent
   
    context_block = (
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": " | ".join(context_parts)}],  # Combine context snippets
        }
        if context_parts
        else None  # Skip the context block if no metadata was provided
    )

    # Build action buttons for invoice and order links
    action_elements: list[dict[str, object]] = []  # Build button set when links are available
    
    if invoice_url:
        action_elements.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Invoice", "emoji": True},
                "style": "primary",
                "url": invoice_url,  # Deep link to the invoice document
            }
        )
    
    if order_url:
        action_elements.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Order", "emoji": True},
                "url": order_url,  # Deep link to the order management record
            }
        )
    action_block = (
        {"type": "actions", "elements": action_elements} if action_elements else None  # Slack requires non-empty actions
    )


    # ----------------------------------------------------------------------
    # ----------------------- Assemble and send message ---------------------
    # ----------------------------------------------------------------------
    
    blocks: list[dict[str, object]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📬 New Purchase Order Processed", "emoji": True},  # Main title
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "A new order has been successfully processed and invoiced."},  # Intro summary
        },
        {"type": "divider"},
        {"type": "section", "fields": field_blocks},  # Summary metrics section
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Order Items:*\n{order_items_text}"},  # Itemized detail section
        },
    ]

    if context_block:
        blocks.extend([{"type": "divider"}, context_block])  # Append optional context
  
    if action_block:
        blocks.extend([{"type": "divider"}, action_block])  # Append optional calls-to-action


    message = {"blocks": blocks}  # Final payload for Slack
    webhook = os.getenv("SLACK_WEBHOOK_URL")  # Resolve webhook with override support
    response = requests.post(webhook, json=message, timeout=10)  # Call Slack webhook with a conservative timeout

    print(f"Message sent! Status: {response.status_code}")  # Log a simple status for operational visibility
