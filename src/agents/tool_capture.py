"""Small helper utilities for capturing tool responses across agents.

The goal is to collect Azure Search payloads in one place for debugging
without forcing each agent to wire up custom middleware.
"""

import json
from typing import Any
from collections.abc import Awaitable, Callable

from agent_framework import FunctionInvocationContext, FunctionMiddleware
from loguru import logger

# Keep raw call data in-memory for quick inspection.
captured_tool_calls: list[dict[str, Any]] = []

# Accumulate raw search docs for the fact-checker (reset per workflow run).
search_evidence: list[str] = []
_evidence_by_tool: dict[str, list[str]] = {}

# Focus evidence on Azure Search tools by default (avoids unrelated payloads).
# Extend this set if you create new tools that return doc lists you care about.
# _EVIDENCE_TOOL_NAMES: set[str] = {"search_customers", "search_products"}


# Clear evidence between workflow runs to avoid data contamination:
def clear_evidence() -> None:
    """Reset every evidence bucket (collection of related evidence) 
    so each workflow run starts clean, without old data."""
    
    # Keep shared state tiny: just wipe the in-memory collections:
    captured_tool_calls.clear()  # Clear captured tool calls
    search_evidence.clear()  # Clear overall search evidence (docs from search tools)
    _evidence_by_tool.clear()  # Clear per-tool evidence buckets (tool-specific docs)


# Retrieve captured evidence (Azure Search payloads) for requested tool names:
def get_evidence(*tool_names: str) -> list[str]:
    """Return captured evidence for the requested tool names.
    
    If no names are provided we return the entire flattened evidence list,
    which mirrors the behavior used by the retriever/fact-checker chain.
    
    Args:
        tool_names: Variable length argument list of tool names to filter by.
        `*tool_names` means you can pass any number of tool names as separate arguments.
        e.g. get_evidence("search_customers", "search_products", ...) is valid.
    Returns:
        A list of captured evidence documents (as JSON strings).
        Evidence documents are only returned for the specified tool names.
        They are basically the raw Azure Search results captured during tool calls.
    """

    # If no tool names are specified, return all captured evidence:
    if not tool_names:
        return search_evidence.copy()  # Return a copy to avoid external mutation.
   
    docs: list[str] = []  # Accumulate evidence for the specified tool names.
   
    # Collect evidence documents for each requested tool name: 
    for name in tool_names:
        docs.extend(_evidence_by_tool.get(name, []))  # Get docs or empty list if none.
    return docs


# Helper to attach the middleware to multiple agents at once:
def attach_capture_middleware(*agents: Any) -> None:
    """Add the capture middleware to each agent once (idempotent helper).
    It checks if the middleware is already present in each agent to avoid duplicates.
    
    Args:
        agents: Variable length argument list of agents to attach middleware to.
        `*` means you can pass any number of agents as separate arguments.
        e.g. attach_capture_middleware(agent1, agent2, ...) is valid.
    Returns:
        None
    """
    for agent in agents:  # Iterate over each provided agent
        if agent is None:
            continue

        # `agent.middleware` may be None/tuple/list. So, we normalize it to a list.
        current = list(getattr(agent, "middleware", []) or [])

        # Avoid adding duplicate middleware instances.
        if any(isinstance(mw, ToolCaptureMiddleware) for mw in current):
            continue

        current.append(ToolCaptureMiddleware())  # Add our middleware to the chain.
        agent.middleware = current  # Re-assign the updated middleware list back to agent


class ToolCaptureMiddleware(FunctionMiddleware):
    """General middleware that logs tool calls and stores raw doc results."""

    async def process(
        self,
        context: FunctionInvocationContext,  # tool call context (name, args, result etc.)
        next: Callable[[FunctionInvocationContext],
                       Awaitable[None]],  # The next middleware/tool in the chain
    ) -> None:
        """Let the tool run, then save the inputs/outputs for debugging."""
        import time
        
        tool_name = context.function.name  # Name supplied when the tool was registered.
        start_time = time.perf_counter()
        
        logger.info("Tool invocation started! Calling the function: '{}'",
                    tool_name)
        
        await next(context)  # Let the underlying tool run normally first.
        
        # Calculate execution time
        duration_ms = (time.perf_counter() - start_time) * 1000
              
        # Log tool execution
        logger.info(
            "Tool execution complete for function '{}' | Duration: {}ms",
            tool_name, duration_ms)

        # NOW get the result after the tool has executed
        tool_result = json.dumps(context.result, indent=3, ensure_ascii=False)
        # tool_metadata = context.metadata
        tool_arguments = context.arguments
        # Persist any evidence we care about so downstream agents can reuse it.
        # serialized_results = [
        #     json.dumps(doc, ensure_ascii=False, default=str)
        #     for doc in tool_result
        # ]
        
        # Extend list by appending elements from the iterable.
        # search_evidence.extend(serialized_results)

        # bucket = _evidence_by_tool.setdefault(tool_name, [])
        # bucket.extend(serialized_docs)

        # logger.debug("Tool result(s) captured from tool name: {} ", tool_name)
        # logger.debug("Number of results captured: {}", len(tool_result))

        # logger.opt(colors=True).debug("<yellow>'{}' function's *metadata*:\n{}</yellow>",
        #                                tool_name, tool_metadata)
        logger.opt(colors=True).debug("<yellow>'{}' function's args:</yellow>\n{}",
                                       tool_name, tool_arguments)
        logger.opt(colors=True).debug("<yellow>'{}' function's captured result(s):</yellow>\n{}",
                                       tool_name, tool_result)

        # record = {
        #     "tool": tool_name,  # Which tool (function) was used
        #     "arguments": dict(context.arguments),  # Inputs the agent provided
        #     "result": tool_result,  # Raw output result (payload)
        #     "duration_ms": duration_ms,
        # }

        # captured_tool_calls.append(record)  # Make data available to other modules.
        
        # Log summary stats
        # logger.debug("<yellow>Capture summary | total_calls={}</yellow>", len(captured_tool_calls))
        # logger.debug("<yellow>Capture summary | evidence_docs={}</yellow>", len(search_evidence))
        # logger.debug("<yellow>Capture summary | captured_tool_calls={}</yellow>", captured_tool_calls)
        # logger.debug("<yellow>Capture summary | search_evidence={}</yellow>", search_evidence)
        # # logger.debug("<yellow>Capture summary | record={}</yellow>", record)
        # logger.debug("<yellow>Capture summary | tool_result={}</yellow>", tool_result)