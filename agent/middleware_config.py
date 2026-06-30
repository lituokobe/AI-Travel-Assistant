"""
Sub-agent middleware configuration.

Provides factory functions for standard middleware, injected when creating agents.
"""

from deepagents.middleware.summarization import (
    create_summarization_tool_middleware,
)
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)


def create_main_agent_middleware(model, backend) -> list:
    """
    Create a middleware list for the main agent.

    Includes:
    - SummarizationToolMiddleware: Actively compresses context after phase completion
    - ModelCallLimitMiddleware: Prevents infinite loops (max 50 model calls)
    - ToolCallLimitMiddleware: Prevents excessive tool calls (max 200 calls)

    Args:
        model: Model used for summary generation (a small model like deepseek-v4-flash is recommended)
        backend: File system backend (used for summary persistence)

    Returns:
        List of middleware instances
    """
    return [
        create_summarization_tool_middleware(model, backend),
        ModelCallLimitMiddleware(run_limit=50),
        ToolCallLimitMiddleware(run_limit=200),
    ]


def create_sub_agent_middleware() -> list:
    """
    Create a middleware list for the sub-agents.

    Only call limits are needed to prevent abnormal loops.

    Returns:
        List of middleware instances
    """
    return [
        ModelCallLimitMiddleware(run_limit=20),
        ToolCallLimitMiddleware(run_limit=50),
    ]