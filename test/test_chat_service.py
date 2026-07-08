"""Tests for chat service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from api_view.models.requests import ResumeRequest, UserContext
from api_view.services.chat_service import ChatService


@pytest.fixture
def chat_service():
    return ChatService()


@pytest.mark.asyncio
async def test_chat_returns_response(chat_service, sample_user_context):
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(
        return_value={"messages": [HumanMessage(content="hi"), AIMessage(content="hello")]}
    )
    mock_agent.aget_state = AsyncMock(return_value=MagicMock(interrupts=[]))

    with (
        patch("api_view.services.chat_service.lifecycle_manager") as mgr,
        patch("api_view.services.chat_service.ensure_session"),
        patch("api_view.services.chat_service.touch_session"),
        patch("api_view.services.chat_service.new_thread_id", return_value="tid-1"),
    ):
        mgr.ensure_ready = AsyncMock(return_value=mock_agent)
        response = await chat_service.chat("Book a flight", None, sample_user_context)

    assert response.thread_id == "tid-1"
    assert len(response.messages) == 2
    mock_agent.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_yields_events(chat_service, sample_user_context):
    async def fake_stream(*args, **kwargs):
        yield 'data: {"type":"token","content":"Hi","source":"main"}\n\n'
        yield 'data: {"type":"done","thread_id":"tid-2","content":"Hi"}\n\n'

    mock_agent = MagicMock()
    with (
        patch("api_view.services.chat_service.lifecycle_manager") as mgr,
        patch("api_view.services.chat_service.ensure_session"),
        patch("api_view.services.chat_service.touch_session"),
        patch("api_view.services.chat_service.map_agent_stream", fake_stream),
        patch("api_view.services.chat_service.new_thread_id", return_value="tid-2"),
    ):
        mgr.ensure_ready = AsyncMock(return_value=mock_agent)
        chunks = [c async for c in chat_service.stream("Hello", None, sample_user_context)]

    assert len(chunks) == 2
    assert "token" in chunks[0]


@pytest.mark.asyncio
async def test_resume_invokes_command(chat_service, sample_user_context):
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="done")]})
    mock_agent.aget_state = AsyncMock(return_value=MagicMock(interrupts=[]))

    request = ResumeRequest(
        thread_id="tid-3",
        resume_value="ticket_no=123",
        user=sample_user_context,
    )

    with (
        patch("api_view.services.chat_service.lifecycle_manager") as mgr,
        patch("api_view.services.chat_service.touch_session"),
    ):
        mgr.ensure_ready = AsyncMock(return_value=mock_agent)
        response = await chat_service.resume(request)

    assert response.thread_id == "tid-3"
    mock_agent.ainvoke.assert_awaited_once()
