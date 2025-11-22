#!/usr/bin/env python3
"""
Slack bot setup helper - saves bot token and approval channel to .env.
No manifest API or admin tokens needed.
"""

from math import log
import os
from pathlib import Path

from dotenv import load_dotenv, set_key
from loguru import logger
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"

def test_bot_token(token: str) -> bool:
    """Verify the bot token works by calling auth.test."""
    try:
        client = WebClient(token=token)
        response = client.auth_test()
        logger.success(f"✓ Token valid. Bot user: {response['user']}")
        return True
    except SlackApiError as e:
        logger.error(f"✗ Token invalid: {e.response['error']}")
        return False


def find_channel_id(token: str, channel_name: str) -> str:
    """Look up channel ID by name (excludes archived channels)."""
    client = WebClient(token=token)
    try:
        response = client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
            limit=200
        )
        channels = response.get("channels", [])
        for channel in channels:
            if channel.get("name") == channel_name:
                return channel["id"]
        return ""
    except SlackApiError:
        return ""


def slack_setup_flow() -> dict:
    """Interactive Slack bot setup."""
    bot_token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    
    if not bot_token:
        logger.info(
            "\nSLACK_BOT_TOKEN missing in `.env`. Create a Slack App at "
            "https://api.slack.com/apps?new_app=1 and add a Bot User with necessary scopes.\n"
            "Recommended scopes: chat:write, channels:read, groups:read, im:read, mpim:read\n"
            "Install the app to your workspace to get the 'Bot User OAuth Token'.\n"
        )
        
        bot_token = input("Please paste the 'Bot User OAuth Token' (xoxb-...): ").strip()

        while not bot_token.startswith("xoxb-") or (len(bot_token) < 15):
            logger.error("Invalid token format (must start with xoxb-) or empty. Please try again.\n")
            
            bot_token = input(
                "Please paste the valid 'Bot User OAuth Token' (xoxb-...): "
            ).strip()
        
        # Save the bot token to .env
        set_key(ENV_FILE, "SLACK_BOT_TOKEN", bot_token)

        logger.success("Saved Slack Bot User OAuth Token to SLACK_BOT_TOKEN in `.env`.")
    else:
        logger.warning(
            "An existing SLACK_BOT_TOKEN found in `.env` and will be re-used. "
            "If you want to use a different token, replace it in the `.env` file manually."
        )

    logger.info("Now testing the Slack Bot token...")
    if not test_bot_token(bot_token):
        logger.warning(
            "The provided Slack Bot token is not working. Please add a valid token manually to the `.env` file.")
    

    # Get Slack's CHANNEL:
    existing_channel = os.getenv("SLACK_APPROVAL_CHANNEL", "").strip()
    if existing_channel:
        logger.warning(
            f"An existing SLACK_APPROVAL_CHANNEL found in `.env`: {existing_channel}."
            "It will be used as the default channel for approval prompts. "
        )
        logger.warning(
            "If you want to use a different channel, you can manually "
            "change it in the `.env` file."
        )

    default_channel = existing_channel.lstrip("#") or "orders"
    
    channel_name = input(
        "\nEnter Slack's Sales approval channel name (without #), or the channel ID "
        "(starts with 'C'), or press enter to use the 'orders' channel: "
    ).strip() or default_channel
    
    channel_id = channel_name if channel_name.startswith("C") \
        else find_channel_id(bot_token, channel_name)
    
    while not channel_id:
        logger.warning(
            f"Channel {channel_name} not found. Make sure the bot is invited to that channel first!")
        
        channel_id = input("Paste channel ID (starts with C): ").strip()
    
    # while not channel_id.startswith("C"):
    #     logger.error("Invalid channel ID. It should start with 'C'. Please try again.")
    #     channel_id = input("Paste channel ID (starts with C): ").strip()
    
    set_key(ENV_FILE, "SLACK_APPROVAL_CHANNEL", channel_id)
    logger.success("Saved Slack Approval Channel ID to SLACK_APPROVAL_CHANNEL in `.env`.")

    logger.info("\n" + "="*60)
    logger.info("Setup complete!")
    logger.info(f"Channel: #{channel_name} | Token: saved")
    logger.info("="*60)
    
    return {"SLACK_BOT_TOKEN": bot_token,
            "SLACK_APPROVAL_CHANNEL": channel_id}


if __name__ == "__main__":
    slack_setup_flow()
