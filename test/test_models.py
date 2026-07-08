"""Tests for API request/response models."""

from api_view.models.events import (
    StreamInterruptEvent,
    StreamPlanEvent,
    StreamReasoningEvent,
    StreamThinkingEvent,
)
from api_view.models.requests import ChatRequestWithContext, ResumeRequest, UserContext


def test_user_context_model():
    user = UserContext(user_id="u1", username="Alice", passenger_id="p1")
    assert user.passenger_id == "p1"


def test_chat_request_with_context():
    req = ChatRequestWithContext(
        message="hello",
        thread_id="t1",
        user=UserContext(user_id="u1", username="Alice"),
    )
    assert req.message == "hello"
    assert req.user.user_id == "u1"


def test_resume_request():
    req = ResumeRequest(
        thread_id="t1",
        resume_value={"decisions": [{"type": "approve"}]},
        user=UserContext(user_id="u1", username="Alice"),
    )
    assert req.resume_value["decisions"][0]["type"] == "approve"


def test_stream_event_defaults():
    assert StreamThinkingEvent(content="step").type == "thinking"
    assert StreamReasoningEvent(content="why").type == "reasoning"
    assert StreamPlanEvent().type == "plan"
    assert StreamInterruptEvent(
        interrupt_id="i1",
        interrupt_type="approval",
        thread_id="t1",
    ).type == "interrupt"
