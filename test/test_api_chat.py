"""Tests for chat API routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agent.schema import ChatResponse, Message
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


def test_chat_requires_ready_agent(client):
    lifecycle_manager._state = AgentState.UNINITIALIZED
    lifecycle_manager._agent = None
    resp = client.post("/api/v1/chat", json={"message": "hello"})
    assert resp.status_code == 503


def test_chat_success(client):
    fake_response = ChatResponse(
        thread_id="tid-1",
        messages=[Message(id="1", role="assistant", content="Hi")],
    )
    with patch("api_view.api.chat.chat_service.chat", AsyncMock(return_value=fake_response)):
        resp = client.post(
            "/api/v1/chat",
            json={"message": "hello"},
            headers={"X-User-Id": "u1", "X-Username": "Alice"},
        )
    assert resp.status_code == 200
    assert resp.json()["thread_id"] == "tid-1"


def test_chat_stream_returns_event_stream(client):
    async def fake_stream(*args, **kwargs):
        yield 'data: {"type":"done","thread_id":"t1","content":""}\n\n'

    with patch("api_view.api.chat.chat_service.stream", fake_stream):
        resp = client.post("/api/v1/chat/stream", json={"message": "hello"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_resume_chat(client, sample_user_context):
    fake_response = ChatResponse(thread_id="tid-2", messages=[])
    with patch("api_view.api.chat.chat_service.resume", AsyncMock(return_value=fake_response)):
        resp = client.post(
            "/api/v1/chat/resume",
            json={
                "thread_id": "tid-2",
                "resume_value": "approved",
                "user": sample_user_context.model_dump(),
            },
        )
    assert resp.status_code == 200
    assert resp.json()["thread_id"] == "tid-2"
