#!/usr/bin/env python3
"""
Gmail OAuth authentication helper.

This script generates the token.json file required for container deployment.
Must be run locally BEFORE deploying to Azure Container Apps because the
OAuth flow requires browser interaction (impossible in headless containers).

Usage:
    python scripts/authenticate_gmail.py

What it does:
    1. Opens browser for Gmail login
    2. Asks you to authorize the app
    3. Creates cred/token.json with refresh_token
    4. This token will be deployed as encrypted secret

The refresh_token in token.json allows the container to access Gmail
without user interaction by automatically refreshing the access_token.
"""

import sys
from pathlib import Path
from loguru import logger

BASE_DIR = Path(__file__).resolve().parents[1]
TOKEN_FILE = BASE_DIR / "cred" / "token.json"

# This would allow imports from ./src/ :
sys.path.insert(0, str(BASE_DIR))

from src.emailing.gmail_tools import _authenticate_gmail


def main():
    """Authenticate and generate token.json."""
    logger.info("="*70)
    logger.info("Gmail OAuth Authentication")
    logger.info("="*70)
    logger.info("This will open your browser to authenticate with Gmail.")
    logger.info("After authorization, token.json will be created with a refresh_token")
    logger.info("that allows unattended Gmail access in the container.\n")
    
    if TOKEN_FILE.exists():
        logger.warning(f"token.json file already exists: {TOKEN_FILE}")

        if input("Delete and re-authenticate? [y/N]: ").strip().lower() != 'y':
            logger.info("Keeping existing token. Exiting.")
            return
        
        TOKEN_FILE.unlink()
        logger.info("Deleted existing token.json")
    
    logger.info("Starting OAuth flow (browser should open shortly)...")
    
    try:
        _authenticate_gmail()
        
        if TOKEN_FILE.exists():
            logger.success("\n" + "="*70)
            logger.success("SUCCESS: token.json created!")
            logger.success(f"Location: {TOKEN_FILE}")
            logger.success("\nThis token enables unattended Gmail access in the container.")
            logger.success("\nToken will be stored as encrypted Container App secret.")
            logger.success("="*70)
        else:
            logger.error("Authentication succeeded but token.json was not created")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        logger.error("\nTroubleshooting:")
        logger.error("  1. Ensure cred/credentials.json exists (from GCP Console)")
        logger.error("  2. Verify OAuth consent screen is configured")
        logger.error("  3. Check Desktop OAuth client is created")
        sys.exit(1)


if __name__ == "__main__":
    main()
