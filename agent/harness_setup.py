"""Register DeepAgents harness profiles for this project."""

from __future__ import annotations

from deepagents import HarnessProfile, register_harness_profile


def register_travel_harness_profiles() -> None:
    """Disable automatic summarization middleware (checkpoint corruption risk).

    DeepAgents adds ``SummarizationMiddleware`` to every agent/sub-agent by
    default. Nested summarization LLM calls and overflow tail writes can produce
    message deltas that fail checkpoint replay
    (``Message as a sequence must be (role string, template)``).

    We keep on-demand ``compact_conversation`` on the main agent only (see
    ``agent/middlewares/tools_summarization.py``); auto compaction is excluded
    for both main and sub-agent model profiles.
    """
    no_auto_summarize = HarnessProfile(
        excluded_middleware={"SummarizationMiddleware"},
    )
    for key in (
        "openai:deepseek-v4-pro",
        "openai:deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    ):
        register_harness_profile(key, no_auto_summarize)
