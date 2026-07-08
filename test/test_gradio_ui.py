"""Tests for Gradio UI helpers."""

from gradio_ui.app import _format_thinking_event


def test_format_thinking_event_reasoning():
    text = _format_thinking_event(
        {"type": "thinking", "category": "reasoning", "content": "Planning...", "source": "main"}
    )
    assert "REASONING" in text or "reasoning" in text.lower()
    assert "Planning..." in text


def test_format_reasoning_event():
    text = _format_thinking_event({"type": "reasoning", "content": "Step 1", "source": "main"})
    assert "Step 1" in text


def test_format_plan_event():
    text = _format_thinking_event(
        {
            "type": "plan",
            "todos": [{"status": "pending", "content": "Search flights"}],
        }
    )
    assert "Search flights" in text


def test_format_interrupt_event():
    text = _format_thinking_event(
        {"type": "interrupt", "interrupt_type": "approval", "payload": {"tool": "flights_cancel"}}
    )
    assert "INTERRUPT" in text
