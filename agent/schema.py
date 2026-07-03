"""
Custom data structure definitions.

Contains type definitions for runtime context, user preferences, and related models.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from pydantic import Field, BaseModel


@dataclass
class TravelContext:
    """
    Runtime context passed in by the caller during invoke().

    Used to provide basic information such as the current user's identity.

    Passed from FastAPI or the frontend.
    In this project, see:
    - api_view/agent_loader.py/create_config()
    - api_view/api/chat.py/stream_chat_response()
    """

    user_id: str  # Required. Unique identifier of the user.
    username: str  # Required. User's display name or login name.


class UserPreferences(BaseModel):
    """
    Long-term user profile.
    Stored in long-term memory and continuously updated as the agent learns
    about the user's travel habits and preferences.
    """
    # Identity
    base_city: str | None = None
    passport_nationality: str | None = None

    # Localization
    preferred_language: str | None = None
    preferred_currency: str | None = None

    # Memberships
    airline_memberships: list[str] = Field(default_factory=list)
    hotel_memberships: list[str] = Field(default_factory=list)

    # Travel preferences
    preferred_travel_types: list[str] = Field(default_factory=list) # 'family', 'business', 'leisure', 'culture', etc
    price_sensitivity: Literal["low", "medium", "high"] | None = None
    special_preferences: list[str] = Field(default_factory=list) # 'vegan', 'no car rental', 'avoid red-eye flights' etc.

    # Communication
    communication_style: Literal["regular","formal","casual","cordial"]| None = None
    recent_destinations: list[str] = Field(default_factory=list)
    recent_queries: list[str] = Field(default_factory=list)

# ============================================================
# Chat-related models
# ============================================================


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(..., description="User message")
    thread_id: str|None = Field(None, description="Conversation ID. A new conversation will be created if omitted.")


class Message(BaseModel):
    """Message model."""

    id: str = Field(..., description="Unique message identifier")
    role: str = Field(..., description="Message role: user/assistant/tool")
    content: str = Field("", description="Message content")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation time")
    tool_calls: list[dict[str, Any]]|None = Field(None, description="Tool call information")
    tool_call_id: str|None = Field(None, description="Tool call ID")
    source: str|None = Field(None, description="Message source: main or sub-agent name")

    # Fields specific to tool messages
    tool_name: str|None = Field(None, description="Tool name")
    tool_status: str|None = Field(None, description="Tool status: calling / done")
    text: str|None = Field(None, description="Tool result text")
    images: list[str]|None = Field(None, description="List of tool result images")
    args: str|None = Field(None, description="Tool call arguments")


class ChatResponse(BaseModel):
    """Chat response model."""

    thread_id: str = Field(..., description="Conversation ID")
    messages: list[Message] = Field(default_factory=list, description="List of messages")


# ============================================================
# Conversation history models
# ============================================================


class Session(BaseModel):
    """Conversation session model."""

    thread_id: str = Field(..., description="Conversation ID")
    title: str = Field(..., description="Conversation title")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Last update time")
    message_count: int = Field(0, description="Number of messages")


class SessionListResponse(BaseModel):
    """Conversation session list response model."""

    sessions: list[Session] = Field(default_factory=list, description="List of conversation sessions")
    total: int = Field(0, description="Total number of sessions")
    page: int = Field(1, description="Current page number")
    limit: int = Field(20, description="Number of items per page")


class SessionMessagesResponse(BaseModel):
    """Conversation message history response model."""

    thread_id: str = Field(..., description="Conversation ID")
    messages: list[Message] = Field(default_factory=list, description="List of messages")


class DeleteSessionResponse(BaseModel):
    """Delete conversation response model."""

    success: bool = Field(True, description="Whether the operation succeeded")
    message: str = Field("Conversation deleted", description="Response message")


# ============================================================
# SSE streaming event models
# ============================================================


class StreamTokenEvent(BaseModel):
    """Token event - A chunk of AI-generated text."""

    type: str = "token"
    content: str = Field(..., description="Text content")
    source: str = Field("main", description="Source: main or sub-agent name")


class StreamToolStartEvent(BaseModel):
    """Tool invocation started event."""

    type: str = "tool_start"
    tool_call_id: str = Field(..., description="Tool call ID")
    tool_name: str = Field(..., description="Tool name")
    source: str = Field("main", description="Source")


class StreamToolArgsEvent(BaseModel):
    """Tool arguments event."""

    type: str = "tool_args"
    args: str = Field(..., description="Tool arguments string")


class StreamToolResultEvent(BaseModel):
    """Tool execution result event."""

    type: str = "tool_result"
    tool_name: str = Field(..., description="Tool name")
    result: str = Field(..., description="Execution result")
    source: str = Field("main", description="Source")


class StreamDoneEvent(BaseModel):
    """Stream completion event."""

    type: str = "done"
    thread_id: str = Field(..., description="Conversation ID")
    content: str = Field("", description="Complete response content")


class StreamErrorEvent(BaseModel):
    """Error event."""

    type: str = "error"
    message: str = Field(..., description="Error message")