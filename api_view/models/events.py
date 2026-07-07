"""Extended SSE event models for planning and interrupt visibility."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class StreamPlanEvent(BaseModel):
    """Agent planning / todo-list update event."""

    type: str = "plan"
    todos: list[dict[str, Any]] = Field(default_factory=list, description="Todo items")
    source: str = Field("main", description="Agent source")


class StreamThinkingEvent(BaseModel):
    """Agent reasoning or delegation step."""

    type: str = "thinking"
    category: Literal["delegation", "plan", "tool", "status", "reasoning"] = "status"
    content: str = Field(..., description="Human-readable thinking step")
    source: str = Field("main", description="Agent source")
    metadata: dict[str, Any] = Field(default_factory=dict)


class StreamReasoningEvent(BaseModel):
    """Model chain-of-thought token (DeepSeek thinking mode)."""

    type: str = "reasoning"
    content: str = Field(..., description="Reasoning text chunk")
    source: str = Field("main", description="Agent source")


class StreamInterruptEvent(BaseModel):
    """Human-in-the-loop interrupt event."""

    type: str = "interrupt"
    interrupt_id: str = Field(..., description="Interrupt identifier")
    interrupt_type: str = Field(..., description="travel_info_request | approval")
    payload: dict[str, Any] = Field(default_factory=dict)
    thread_id: str = Field(..., description="Conversation ID")
