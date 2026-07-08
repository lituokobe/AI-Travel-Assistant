"""Tests for session API routes."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent.schema import SessionListResponse, SessionMessagesResponse, Session
from api_view.agent_loader import lifecycle_manager


@pytest.fixture
def client(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(lifecycle_manager, "initialize", AsyncMock())
    monkeypatch.setattr(lifecycle_manager, "shutdown", AsyncMock())

    from api_view.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_list_sessions(client):
    now = datetime.now(timezone.utc)
    fake = SessionListResponse(
        sessions=[
            Session(
                thread_id="t1",
                title="Flights",
                created_at=now,
                updated_at=now,
                message_count=2,
            )
        ],
        total=1,
        page=1,
        limit=20,
    )
    with patch("api_view.api.sessions.sessions_svc.list_sessions", return_value=fake):
        resp = client.get("/api/v1/sessions", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_get_session_messages(client):
    fake = SessionMessagesResponse(thread_id="t1", messages=[])
    with patch("api_view.api.sessions.sessions_svc.get_session_messages", return_value=fake):
        resp = client.get("/api/v1/sessions/t1")
    assert resp.status_code == 200
    assert resp.json()["thread_id"] == "t1"


def test_delete_session_not_found(client):
    with patch("api_view.api.sessions.sessions_svc.delete_session", return_value=False):
        resp = client.delete("/api/v1/sessions/missing")
    assert resp.status_code == 404


def test_delete_session_success(client):
    with patch("api_view.api.sessions.sessions_svc.delete_session", return_value=True):
        resp = client.delete("/api/v1/sessions/t1")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
