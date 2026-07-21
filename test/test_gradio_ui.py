"""Tests for Gradio UI helpers."""

from gradio_ui.app import (
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


def test_skips_reasoning_and_thinking():
    assert _format_process_event({"type": "reasoning", "content": "hmm"}) is None
    assert (
        _format_process_event(
            {"type": "thinking", "category": "tool", "content": "Calling tool: x"}
        )
        is None
    )


def test_process_chat_message_is_thought():
    msg = _process_chat_message("**Tool call:** `hotels_search`")
    assert msg["role"] == "assistant"
    assert msg["content"] == "**Tool call:** `hotels_search`"
    assert msg["metadata"]["title"] == "Working…"
    assert "Working…" not in msg["content"]


def test_pretty_payload_json():
    out = _pretty_payload('{"a": 1}', 200)
    assert '"a"' in out
