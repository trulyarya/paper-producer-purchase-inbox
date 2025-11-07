"""Capture and log raw Azure Search tool responses for retriever debugging."""

import json
# from datetime import datetime
# from pathlib import Path
from typing import Any

# collections.abc is a module that provides abstract base classes:
# `Awaitable` means a type that can be awaited,
# `Callable` means that it is a function that can be called.
from collections.abc import Awaitable, Callable 

import sys
from loguru import logger

from agent_framework import FunctionInvocationContext, FunctionMiddleware

# Keep raw call data in-memory for quick inspection.
captured_tool_calls: list[dict[str, Any]] = []

# Accumulate raw search docs for the fact-checker (reset per workflow run).
search_evidence: list[str] = []


# _log_file.parent.mkdir(parents=True, exist_ok=True)


# Set up Loguru logging to a file with timestamp in filename
_log_file = "logs/tool_capture_{time}.log"

# Loguru ships with colorful console sink already; we only add a file "sink" here:
logger.add(
    _log_file,
    level="DEBUG",
    format="{time} {message}",
    encoding="utf-8",
)

# logger.add(
#     sys.stdout,
#     level="DEBUG",
#     colorize=True,
#     format="<cyan>{time:HH:mm:ss}</cyan> | {message}",
# )

logger.add(
    sys.stdout,
    level="DEBUG",
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> <level>{message}</level>"
)


def clear_evidence() -> None:
    """Reset evidence lists made during workflow to 
    prevent leaking data between workflow runs."""
    # `global` means that we refer to the module-level variables, not local ones.
    # If we didn't declare this, Python treats these names as local variables. 
    global captured_tool_calls, search_evidence
    
    captured_tool_calls.clear()  # Clear list of captured tool calls
    search_evidence.clear()  # Clear list of search evidence


class CaptureSearchMiddleware(FunctionMiddleware):
    """Middleware that stores and logs search tool outputs."""
    async def process(
        self,
        context: FunctionInvocationContext,  # tool call context (name, args, result etc.)
        next: Callable[[FunctionInvocationContext],
                       Awaitable[None]],  # The next middleware/tool in the chain
    ) -> None:
        """Allow the tool call, then capture the result for the search tools."""
        tool_name = context.function.name  # Name supplied when the tool was registered.

        # Tip: Loguru uses `{}` style formatting, keeping it approachable.
        # Log info about the tool call and its result, before execution
        logger.debug(
            "[CaptureSearchMiddleware] BEFORE next() | function: {}",
            tool_name,)
        
        await next(context)  # Let the underlying tool run normally first.
        
        # NOW get the result after the tool has executed
        tool_result = context.result
        
        # Log info about the tool call and its result, after execution
        logger.debug(
            "[CaptureSearchMiddleware] AFTER next() | function: {} | has result: {}",
            tool_name,
            tool_result is not None,)
        
        # Logging how we're capturing the type of result
        logger.debug(
            "[CaptureSearchMiddleware] CAPTURING {} | result type: {}",
            tool_name,
            type(tool_result),)

        # Store each search document individually as JSON string for fact-checking
        if isinstance(tool_result, list):
            for doc in tool_result:  # Each doc is a dict
                search_evidence.append(json.dumps(doc, ensure_ascii=False))

        record = {
            "tool": tool_name,  # Which tool (function) was used
            "arguments": dict(context.arguments),  # Inputs the agent provided
            "result": tool_result,  # Raw output result (payload)
        }

        captured_tool_calls.append(record)  # Make data available to other modules.
        
        # Logging the record we've captured
        logger.debug("[CaptureSearchMiddleware] RECORD {}", record)

        # Here we log the record to file
        logger.debug("[CaptureSearchMiddleware] Logged to file: {}", _log_file)
        
        # Finally, we log the totals of captured calls and evidence docs
        logger.debug(
            "[CaptureSearchMiddleware] Totals | captured: {} | evidence docs: {}",
            len(captured_tool_calls),
            len(search_evidence),)


