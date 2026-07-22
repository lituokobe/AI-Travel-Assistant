"""Tests for Gradio UI helpers."""

from gradio_ui.app import (
    _OPTION_APPROVE,
    _OPTION_REJECT,
    _approval_actions,
    _build_interrupt_reply,
    _format_process_event,
    _pretty_payload,
    _process_chat_message,
)


def test_format_plan_event():
    text = _format_process_event(
        {
            "type": "plan",
            "todos": [{"status": "pending", "content": "Search hotels in Paris"}],
        }
    )
    assert text is not None
    assert "Todo list" in text
    assert "Search hotels in Paris" in text


def test_format_tool_start_no_id():
    text = _format_process_event({"type": "tool_start", "tool_name": "hotels_search"})
    assert text == "**Tool call:** `hotels_search`"
    assert "source=" not in text
    assert "model:" not in text


def test_format_tool_start_with_agent_source():
    text = _format_process_event(
        {
            "type": "tool_start",
            "tool_name": "hotels_search",
            "source": "hotels-agent",
        }
    )
    assert text == "**Tool call** (`hotels-agent`): `hotels_search`"


def test_format_tool_args_skips_empty():
    assert _format_process_event({"type": "tool_args", "args": "{}"}) is None
    assert _format_process_event({"type": "tool_args", "args": ""}) is None


def test_format_tool_result():
    text = _format_process_event(
        {
            "type": "tool_result",
            "tool_name": "hotels_search",
            "result": '[{"id": 1, "name": "Hilton"}]',
        }
    )
    assert text is not None
    assert "Tool result" in text
    assert "hotels_search" in text
    assert "Hilton" in text


def test_format_agent_switch_thinking():
    text = _format_process_event(
        {
            "type": "thinking",
            "category": "status",
            "content": "Current: hotels-agent",
            "metadata": {"kind": "agent_switch", "agent": "hotels-agent"},
        }
    )
    assert text == "**Current:** hotels-agent"


def test_format_delegation_thinking():
    text = _format_process_event(
        {
            "type": "thinking",
            "category": "delegation",
            "content": "Delegating to hotels-agent",
        }
    )
    assert text is not None
    assert "Handover" in text
    assert "hotels-agent" in text


def test_skips_tool_reasoning_thinking():
    assert _format_process_event({"type": "reasoning", "content": "hmm"}) is None
    assert (
        _format_process_event(
            {"type": "thinking", "category": "tool", "content": "Calling tool: x"}
        )
        is None
    )
    assert (
        _format_process_event(
            {"type": "interrupt", "interrupt_type": "approval"}
        )
        is None
    )


def test_process_chat_message_is_thought():
    msg = _process_chat_message("**Tool call:** `hotels_search`")
    assert msg["role"] == "assistant"
    assert msg["content"] == "**Tool call:** `hotels_search`"
    assert msg["metadata"]["title"] == "Working…"
    assert "Working…" not in msg["content"]


def test_build_approval_interrupt_reply_has_options():
    reply = _build_interrupt_reply(
        {
            "type": "interrupt",
            "interrupt_type": "approval",
            "payload": {
                "actions": [
                    {
                        "name": "hotels_book",
                        "args": {"hotel_id": 1, "user_id": "3442 587242"},
                    }
                ]
            },
        }
    )
    assert reply["role"] == "assistant"
    assert "hotels_book" in reply["content"]
    assert "Approve" in reply["content"] or "approval" in reply["content"].lower()
    values = {o["value"] for o in reply["options"]}
    assert values == {_OPTION_APPROVE, _OPTION_REJECT}


def test_build_travel_info_interrupt_reply():
    reply = _build_interrupt_reply(
        {
            "interrupt_type": "travel_info_request",
            "payload": {
                "missing_fields": "check_in",
                "collected_data": "destination=Paris",
            },
        }
    )
    assert "check_in" in reply["content"]
    assert "Paris" in reply["content"]
    assert "options" not in reply


def test_approval_actions_fallback_to_action_requests():
    actions = _approval_actions(
        {"action_requests": [{"name": "hotels_book", "args": {"hotel_id": 9}}]}
    )
    assert actions[0]["name"] == "hotels_book"
    assert actions[0]["args"]["hotel_id"] == 9


def test_pretty_payload_json():
    out = _pretty_payload('{"a": 1}', 200)
    assert '"a"' in out
