"""API request models extending agent/schema.py types."""

from typing import Any

from pydantic import BaseModel, Field

from agent.schema import ChatRequest


class UserContext(BaseModel):
    """Per-request user identity passed from client."""

    user_id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Display name")
    passenger_id: str | None = Field(
        None,
        description="Passenger ID for flight MCP tools (injected into configurable)",
    )


class ChatRequestWithContext(ChatRequest):
    """Chat request with user context."""

    user: UserContext


class ResumeRequest(BaseModel):
    """Resume an interrupted agent run."""

    thread_id: str = Field(..., description="Conversation ID")
    resume_value: Any = Field(
        ...,
        description=(
            "Resume payload. For travel_info_request: user text or dict. "
            "For approval interrupts: {\"decisions\": [{\"type\": \"approve\"}]}"
        ),
    )
    user: UserContext


class AgentInitRequest(BaseModel):
    """Optional agent initialization parameters."""

    sandbox_id: str | None = Field(None, description="Reuse an existing sandbox ID")
