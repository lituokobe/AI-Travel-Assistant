"""Override agent LLM config at runtime without modifying agent/config.py."""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

import agent.config as agent_config
from api_view.config import PROJECT_DIR

# Ensure .env is loaded before reading keys (agent.config also loads it)
from dotenv import load_dotenv

load_dotenv(PROJECT_DIR / ".env", override=True)

ENABLE_MODEL_THINKING = os.getenv("ENABLE_MODEL_THINKING", "true").lower() in (
    "1",
    "true",
    "yes",
)


def _thinking_extra_body(enabled: bool) -> dict:
    return {"thinking": {"type": "enabled" if enabled else "disabled"}}


def apply_model_overrides() -> dict[str, bool]:
    """Patch agent.config models before create_main_agent() runs."""
    thinking_type = "enabled" if ENABLE_MODEL_THINKING else "disabled"

    agent_config.MAIN_MODEL = ChatOpenAI(
        model="deepseek-v4-pro",
        temperature=1.1,
        api_key=agent_config.DEEPSEEK_API_KEY,
        base_url=agent_config.DEEPSEEK_BASE_URL,
        max_tokens=2560000,
        extra_body=_thinking_extra_body(ENABLE_MODEL_THINKING),
    )

    # Summary model stays fast — thinking off for background memory updates
    agent_config.SUMMARY_MODEL = ChatOpenAI(
        model="deepseek-v4-flash",
        temperature=0.3,
        api_key=agent_config.DEEPSEEK_API_KEY,
        base_url=agent_config.DEEPSEEK_BASE_URL,
        max_tokens=2560000,
        extra_body=_thinking_extra_body(False),
    )

    return {
        "main_thinking": ENABLE_MODEL_THINKING,
        "summary_thinking": False,
        "thinking_type": thinking_type,
    }
