"""
Runtime context injection middleware.

Extracts user_id and username from runtime.context and injects them as a
SystemMessage when the Agent starts. This allows the Agent to know the 
current user's identity without calling any tools, so it can correctly 
read from and write to /memories/{user_id}/preferences.md.

Usage:
from agent.middlewares.context_injection import ContextInjectionMiddleware
middleware = ContextInjectionMiddleware()
"""

from __future__ import annotations

from typing import Any
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from agent.logger import logger


class ContextInjectionMiddleware(AgentMiddleware):
    """Inject user_id and username from runtime.context at the beginning of the conversation."""

    def before_agent(
        self, state: dict[str, Any], runtime: Any
    ) -> dict[str, Any]|None:
        """Synchronous version: inject the user context as a SystemMessage."""
        ctx = getattr(runtime, "context", None)
        if ctx is None:
            logger.warning("ContextInjectionMiddleware: runtime.context is None, skipping context injection")
            return None
        user_id = getattr(ctx, "user_id", None)
        if not user_id:
            logger.warning("ContextInjectionMiddleware: user_id is missing in runtime.context, skipping context injection")
            return None
        username = getattr(ctx, "username", None) or user_id

        logger.info(f"ContextInjectionMiddleware: injecting user context user_id={user_id}, username={username}")

        notice = (
            f"[System Context]\n"
            f"Current user_id: {user_id}\n"
            f"Current username: {username}\n"
            f"User preferences file: /memories/{user_id}/preferences.md\n"
            f"\nPlease first use read_file to read the preferences file above to understand the user's preferences."
            f"\n(recent_destinations and recent_queries are maintained automatically by the system; you do not need to update them manually.)"
        )
        return {"messages": [SystemMessage(content=notice)]}

    async def abefore_agent(
        self, state: dict[str, Any], runtime: Any
    ) -> dict[str, Any]|None:
        """Asynchronous version: inject the user context as a SystemMessage."""
        # Same logic as the synchronous version
        return self.before_agent(state, runtime)
