"""Tests for agent lifecycle helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_view.agent_loader import (
    AgentLifecycleManager,
    AgentState,
    create_config,
    create_travel_context,
    new_thread_id,
)


def test_new_thread_id_is_uuid():
    tid = new_thread_id()
    assert isinstance(tid, str)
    assert len(tid) == 36


def test_create_config_includes_passenger_id():
    config = create_config("thread-1", passenger_id="pass-123")
    assert config["configurable"]["thread_id"] == "thread-1"
    assert config["configurable"]["passenger_id"] == "pass-123"


def test_create_travel_context():
    ctx = create_travel_context("u1", "Alice")
    assert ctx.user_id == "u1"
    assert ctx.username == "Alice"


@pytest.mark.asyncio
async def test_initialize_success(fresh_lifecycle_manager):
    mock_graph = MagicMock()
    with (
        patch("api_view.db_bootstrap.sync_database_dates"),
        patch("api_view.model_override.apply_model_overrides", return_value={"main_thinking": True}),
        patch("api_view.agent_loader.create_main_agent", AsyncMock(return_value=mock_graph)),
    ):
        status = await fresh_lifecycle_manager.initialize()

    assert status["ready"] is True
    assert status["state"] == AgentState.READY.value
    assert fresh_lifecycle_manager.agent is mock_graph


@pytest.mark.asyncio
async def test_initialize_failure_sets_error_state(fresh_lifecycle_manager):
    with (
        patch("api_view.db_bootstrap.sync_database_dates"),
        patch("api_view.model_override.apply_model_overrides", return_value={}),
        patch("api_view.agent_loader.create_main_agent", AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await fresh_lifecycle_manager.initialize()

    assert fresh_lifecycle_manager.state == AgentState.ERROR
    assert fresh_lifecycle_manager.status()["error"] == "boom"


@pytest.mark.asyncio
async def test_shutdown_resets_state(fresh_lifecycle_manager):
    fresh_lifecycle_manager._agent = MagicMock()
    fresh_lifecycle_manager._state = AgentState.READY
    result = await fresh_lifecycle_manager.shutdown()
    assert result["status"] == "shutdown"
    assert fresh_lifecycle_manager.state == AgentState.UNINITIALIZED
