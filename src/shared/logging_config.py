"""Simple centralized logging - configure once, use everywhere.

Fixes the duplicate log issue by configuring loguru ONCE in main.py.
All other modules just import the logger directly.
"""

import sys
from pathlib import Path
from loguru import logger

_configured = False


def configure_logging(level: str = "DEBUG"):
    """Function to configure logging settings.
    Call this ONCE in main.py to set up logging."""
    global _configured
    
    if _configured:
        return
    
    logger.remove()  # Remove default handler
    
    # Console output
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
    )
    
    # File output (rotates daily)
    Path("logs").mkdir(exist_ok=True)
    logger.add(
        "logs/workflow_{time:YYYY-MM-DD_HH-mm-ss}.log",
        level=level,
        rotation="00:00",
        retention="30 days",
    )
    
    _configured = True
    logger.info("Logging configured")
