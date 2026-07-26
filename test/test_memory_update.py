"""Tests for MemoryUpdateMiddleware entity extraction isolation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent.middlewares.memory_update import MEMORY_UPDATE_TAG, _extract_entities


@pytest.mark.asyncio
async def test_extract_entities_uses_human_message_and_isolated_config():
    model = AsyncMock()
    model.ainvoke = AsyncMock(
        return_value=AIMessage(
            content='{"destinations": ["Zurich"], "query": "family trip"}'
        )
    )

    result = await _extract_entities(
        model,
        user_message="Book a package to Zurich",
        ai_summary="Here are your packages…",
    )

    assert result["destinations"] == ["Zurich"]
    assert "family" in result["query"]

    args, kwargs = model.ainvoke.await_args
    messages = args[0]
    assert isinstance(messages, list)
    assert isinstance(messages[0], HumanMessage)
    config = kwargs.get("config") or {}
    assert MEMORY_UPDATE_TAG in (config.get("tags") or [])
    assert config.get("callbacks") == []
    assert config.get("configurable") == {}


@pytest.mark.asyncio
async def test_middleware_aafter_agent_is_noop():
    from agent.middlewares.memory_update import MemoryUpdateMiddleware

    mw = MemoryUpdateMiddleware(model=AsyncMock())
    assert await mw.aafter_agent({"messages": []}, SimpleNamespace()) is None
