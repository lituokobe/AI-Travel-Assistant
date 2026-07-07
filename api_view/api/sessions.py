"""Session management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from agent.schema import DeleteSessionResponse, SessionListResponse, SessionMessagesResponse
from api_view.dependencies import resolve_user_context
from api_view.models.requests import UserContext
from api_view.services import session_service as sessions_svc

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    user: UserContext = Depends(resolve_user_context),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List conversation sessions for the current user."""
    return sessions_svc.list_sessions(user.user_id, page=page, limit=limit)


@router.get("/{thread_id}", response_model=SessionMessagesResponse)
async def get_session_messages(thread_id: str):
    """Get message history for a conversation."""
    return sessions_svc.get_session_messages(thread_id)


@router.delete("/{thread_id}", response_model=DeleteSessionResponse)
async def delete_session(thread_id: str):
    """Delete a conversation and its checkpoints."""
    deleted = sessions_svc.delete_session(thread_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return DeleteSessionResponse(success=True, message="Conversation deleted")
