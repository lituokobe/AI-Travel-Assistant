"""Tests for agent schema models."""

from agent.schema import ChatRequest, Message, TravelContext, UserPreferences


def test_travel_context_dataclass():
    ctx = TravelContext(user_id="u1", username="Bob")
    assert ctx.user_id == "u1"


def test_chat_request_optional_thread():
    req = ChatRequest(message="hi")
    assert req.thread_id is None


def test_user_preferences_defaults():
    prefs = UserPreferences()
    assert prefs.airline_memberships == []
    assert prefs.price_sensitivity is None


def test_message_model():
    msg = Message(id="1", role="user", content="hello")
    assert msg.content == "hello"
