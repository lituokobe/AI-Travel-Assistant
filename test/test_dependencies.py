"""Tests for API dependencies."""

import pytest
from fastapi import HTTPException

from api_view.agent_loader import AgentState, lifecycle_manager
from api_view.dependencies import require_agent_ready, resolve_user_context


@pytest.mark.asyncio
async def test_require_agent_ready_raises_when_not_ready():
    lifecycle_manager._state = AgentState.UNINITIALIZED
    lifecycle_manager._agent = None
    with pytest.raises(HTTPException) as exc:
        await require_agent_ready()
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_require_agent_ready_passes_when_ready():
    lifecycle_manager._state = AgentState.READY
    lifecycle_manager._agent = object()
    await require_agent_ready()


def test_resolve_user_context_defaults():
    ctx = resolve_user_context(None, None, None)
    assert ctx.user_id
    assert ctx.username
    assert ctx.passenger_id == ctx.user_id


def test_resolve_user_context_headers():
    ctx = resolve_user_context("uid", "Name", "pid")
    assert ctx.user_id == "uid"
    assert ctx.username == "Name"
    assert ctx.passenger_id == "pid"


def test_resolve_user_context_passenger_defaults_to_user_id():
    ctx = resolve_user_context("3442 587242", "Luis", None)
    assert ctx.user_id == "3442 587242"
    assert ctx.username == "Luis"
    assert ctx.passenger_id == "3442 587242"
