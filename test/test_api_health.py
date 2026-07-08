"""Tests for FastAPI health endpoints."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from api_view.agent_loader import AgentState, lifecycle_manager


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(lifecycle_manager, "initialize", AsyncMock())
    monkeypatch.setattr(lifecycle_manager, "shutdown", AsyncMock())
    lifecycle_manager._state = AgentState.READY
    lifecycle_manager._agent = object()

    from api_view.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_root_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "AI Travel Assistant API"


def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["agent_state"] == "ready"


def test_readiness_endpoint(client):
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert "redis_uri" in body["checks"]
