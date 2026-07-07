"""Chat endpoints — sync, streaming, and HITL resume."""

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from agent.schema import ChatRequest, ChatResponse
from api_view.dependencies import require_agent_ready, resolve_user_context
from api_view.models.requests import ChatRequestWithContext, ResumeRequest, UserContext
from api_view.services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: UserContext = Depends(resolve_user_context),
    _: None = Depends(require_agent_ready),
):
    """Send a message and receive the full response."""
    return await chat_service.chat(body.message, body.thread_id, user)


@router.post("/with-context", response_model=ChatResponse)
async def chat_with_context(
    body: ChatRequestWithContext,
    _: None = Depends(require_agent_ready),
):
    """Send a message with explicit user context in the body."""
    return await chat_service.chat(body.message, body.thread_id, body.user)


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user: UserContext = Depends(resolve_user_context),
    _: None = Depends(require_agent_ready),
):
    """Stream agent response as Server-Sent Events."""
    return EventSourceResponse(
        chat_service.stream(body.message, body.thread_id, user),
        media_type="text/event-stream",
    )


@router.post("/stream/with-context")
async def chat_stream_with_context(
    body: ChatRequestWithContext,
    _: None = Depends(require_agent_ready),
):
    """Stream with explicit user context in the body."""
    return EventSourceResponse(
        chat_service.stream(body.message, body.thread_id, body.user),
        media_type="text/event-stream",
    )


@router.post("/resume", response_model=ChatResponse)
async def resume_chat(
    body: ResumeRequest,
    _: None = Depends(require_agent_ready),
):
    """Resume an interrupted agent run (HITL)."""
    return await chat_service.resume(body)


@router.post("/resume/stream")
async def resume_chat_stream(
    body: ResumeRequest,
    _: None = Depends(require_agent_ready),
):
    """Resume an interrupted run with SSE streaming."""
    return EventSourceResponse(
        chat_service.resume_stream(body),
        media_type="text/event-stream",
    )
