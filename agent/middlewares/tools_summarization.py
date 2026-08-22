"""
On-demand conversation compaction for the **main agent** only.

DeepAgents' default stack includes automatic ``SummarizationMiddleware`` (compaction
on every model call near the context limit). This project disables that via
``register_travel_harness_profiles()`` in ``agent/harness_setup.py`` because
auto-summarization nested LLM work correlated with corrupted LangGraph message
checkpoints.

What remains on the main agent:

- ``SummarizationToolMiddleware`` from ``create_summarization_tool_middleware``
- Tool: ``compact_conversation`` — explicit compaction when the model invokes it
- A small system-prompt nudge to use the tool on long sessions
- An internal summarization engine used **only** by that tool (not registered as
  auto middleware on the stack)

Sub-agents do **not** get this middleware; they should return concise reports and
let the main agent compact the thread when needed.

Operational guidance (see ``AGENTS.md``): call ``compact_conversation`` after large
sub-agent ``task`` results and on long multi-turn package / change-of-plans flows.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from deepagents.backends import CompositeBackend
from deepagents.middleware.summarization import (
    SummarizationToolMiddleware,
    create_summarization_tool_middleware,
)

# deepagents 0.7.0 removed the built-in ``SUMMARIZATION_SYSTEM_PROMPT`` constant
# and changed the ``system_prompt`` default on ``create_summarization_tool_middleware``
# to ``None`` (no prose injected).  We define the nudge locally to preserve the
# same behaviour the project had on 0.6.x.
_COMPACT_CONVERSATION_NUDGE = """## Compact conversation Tool `compact_conversation`

You have access to a `compact_conversation` tool. This tool refreshes your context window to reduce context bloat and costs.

You should use the tool when:
- The user asks to move on to a completely new task for which previous context is likely irrelevant.
- You have finished extracting or synthesizing a result and previous working context is no longer needed.
"""


def build_summarization_middleware(
    backend: CompositeBackend,
    model: str | BaseChatModel,
) -> SummarizationToolMiddleware:
    """Build main-agent-only on-demand compaction (``compact_conversation``).

    Args:
        backend: Composite backend used to offload evicted history (e.g. under
            ``/conversation_history/`` in the sandbox).
        model: Chat model for summary generation — use ``SUMMARY_MODEL`` (cheap /
            fast) rather than the main reasoning model.

    Returns:
        ``SummarizationToolMiddleware`` to append to ``create_deep_agent(...,
        middleware=[...])``. Do **not** rely on automatic summarization; it is
        excluded by harness profile for ``openai:deepseek-v4-pro`` and
        ``openai:deepseek-v4-flash``.

    Note:
        Eligibility for the tool (minimum context before compact is allowed) uses
        DeepAgents defaults inside the wrapped engine (~half of the auto trigger).
        Tuning requires passing custom args through ``create_summarization_tool_middleware``
        if product needs stricter gates later.
    """
    return create_summarization_tool_middleware(
        model=model,
        backend=backend,
        system_prompt=_COMPACT_CONVERSATION_NUDGE,
    )
