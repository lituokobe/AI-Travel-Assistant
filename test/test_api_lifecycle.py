"""Tests for agent lifecycle API routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api_view.agent_loader import AgentState, lifecycle_manager


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(lifecycle_manager, "initialize", AsyncMock(return_value={"ready": True}))
    monkeypatch.setattr(lifecycle_manager, "shutdown", AsyncMock(return_value={"status": "shutdown"}))
    lifecycle_manager._state = AgentState.UNINITIALIZED
    lifecycle_manager._agent = None

    from api_view.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_agent_status(client):
    lifecycle_manager._state = AgentState.READY
    lifecycle_manager._agent = object()
    resp = client.get("/api/v1/agent/status")
    assert resp.status_code == 200
    assert resp.json()["state"] == "ready"


def test_initialize_agent(client):
    with patch.object(lifecycle_manager, "initialize", AsyncMock(return_value={"ready": True, "state": "ready"})):
        resp = client.post("/api/v1/agent/initialize", json={})
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


def test_shutdown_agent(client):
    with patch.object(lifecycle_manager, "shutdown", AsyncMock(return_value={"status": "shutdown"})):
        resp = client.post("/api/v1/agent/shutdown")
    assert resp.status_code == 200
    assert resp.json()["status"] == "shutdown"
