"""
Summarization middleware factory.

Built on DeepAgents' built-in create_summarization_tool_middleware,
providing the following capabilities:

1. Automatic summarization: Automatically compresses conversation history when
   the context approaches the model's context window limit.
2. On-demand summarization: Provides the compact_conversation tool, allowing
   the Agent to proactively summarize the conversation at key points (such as
   after receiving reports from sub-agents).
"""

from langchain_core.language_models import BaseChatModel
from deepagents.middleware.summarization import create_summarization_tool_middleware
from deepagents.middleware.summarization import SummarizationToolMiddleware
from deepagents.backends import CompositeBackend


def build_summarization_middleware(
    backend: CompositeBackend,
    model: str | BaseChatModel,
) -> SummarizationToolMiddleware:
    """
    Build the summarization tool middleware.

    This middleware is a SummarizationToolMiddleware instance. Internally, it
    automatically includes a SummarizationMiddleware (responsible for automatic
    summarization) and additionally provides a tool named
    `compact_conversation`, which the Agent can invoke to proactively compress
    the conversation.

    Args:
        backend: Sandbox backend used to persist the full conversation history
            that has been summarized.
        model: Model used to generate summaries. This can be either a model
            identifier string or a model instance. It is recommended to use a
            lightweight, low-cost model (such as "gpt-4o-mini") to reduce cost.

    Returns:
        SummarizationToolMiddleware: Can be passed directly to the middleware
        list of create_deep_agent.

    """
    # This factory function automatically creates a SummarizationMiddleware
    # and embeds it into the SummarizationToolMiddleware. Parameters such as
    # the summarization trigger threshold use the framework defaults, which
    # typically trigger automatic summarization when the context reaches 85%
    # of the available context window. This is suitable for most production
    # scenarios.
    return create_summarization_tool_middleware(
        model=model,
        backend=backend
    )