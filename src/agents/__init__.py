from agents.base import chat_client
from agents.email_classifier import classifier
from agents.email_parser import parser
from agents.retriever import retriever
from agents.decider import decider
from agents.fulfiller import fulfiller
from agents.rejector import rejector
from agents.middleware_tools import (
    ToolCaptureMiddleware,
    # This function attaches the middleware to agents like this: attach_middlewares(agent1, agent2, ...)
    attach_middlewares,
)

# Ensure every agent captures tool calls for consistent debugging evidence.
# This is idempotent and will not duplicate middleware if already present.
# We attach the middleware to all relevant agents here.
# This is done at the package level to ensure consistency across all agents,
# including any future agents added to this module.
# It is done here instead of in each agent's module to avoid redundancy.
attach_middlewares(   # Function that attaches middleware to multiple agents
    classifier,
    parser,
    retriever,
    decider,
    fulfiller,
    rejector,
)


__all__ = [
    "classifier",
    "parser",
    "retriever",
    "decider",
    "fulfiller",
    "rejector",
    "chat_client",
    "ToolCaptureMiddleware",
]
