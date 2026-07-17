"""Tests for SSE stream mapping utilities."""

import json

from langchain_core.messages import AIMessageChunk
from langgraph.types import Interrupt

from api_view.services.stream_mapper import (
    _extract_interrupts,
    _extract_reasoning,
    _extract_visible_text,
    _format_tool_args,
    _is_internal_llm_run,
    _normalize_tool_call,
    _strip_trailing_memory_json,
    _thinking_for_tool,
)
from agent.middlewares.memory_update import MEMORY_UPDATE_TAG


def test_format_tool_args_dict():
    assert "SFO" in _format_tool_args({"from": "SFO"})


def test_normalize_tool_call_none_id_uses_index():
    tc_id, name, args = _normalize_tool_call(
        {"id": None, "name": "read_file", "args": {}, "index": 0}
    )
    assert tc_id == "idx-0"
    assert name == "read_file"
    assert isinstance(tc_id, str)


def test_normalize_tool_call_missing_id_and_index_falls_back():
    tc_id, name, _args = _normalize_tool_call({"id": None, "name": "", "args": {}})
    assert tc_id == "anon-tool"
    assert name == ""


def test_normalize_tool_call_preserves_real_id():
    tc_id, name, args = _normalize_tool_call(
        {"id": "call-abc", "name": "flights_fetch", "args": {"passenger_id": "x"}}
    )
    assert tc_id == "call-abc"
    assert name == "flights_fetch"
    assert args["passenger_id"] == "x"


def test_stream_tool_start_event_rejects_none_id_fixed_by_normalize():
    from agent.schema import StreamToolStartEvent

    tc_id, name, _ = _normalize_tool_call(
        {"id": None, "name": "read_file", "index": 1}
    )
    event = StreamToolStartEvent(tool_call_id=tc_id, tool_name=name, source="main")
    assert event.tool_call_id == "idx-1"


def test_strip_trailing_memory_json():
    text = (
        "Would you like to book the Hilton?\n"
        '{"destinations": ["Basel"], "query": "Looking for a luxury hotel"}'
    )
    assert _strip_trailing_memory_json(text) == "Would you like to book the Hilton?"


def test_is_internal_llm_run_detects_memory_tag():
    assert _is_internal_llm_run({"tags": [MEMORY_UPDATE_TAG]})
    assert not _is_internal_llm_run({"tags": ["other"]})
    assert _is_internal_llm_run({"run_name": "memory_entity_extract"})

def test_thinking_for_task_delegation():
    event = _thinking_for_tool("task", {"description": "search flights"}, "main")
    assert event.category == "delegation"
    assert "search flights" in event.content


def test_thinking_for_write_todos():
    event = _thinking_for_tool("write_todos", {"todos": []}, "main")
    assert event.category == "plan"


def test_extract_reasoning_from_additional_kwargs():
    chunk = AIMessageChunk(
        content="",
        additional_kwargs={"reasoning_content": "Let me think..."},
    )
    assert _extract_reasoning(chunk) == "Let me think..."


def test_extract_visible_text_from_string_content():
    chunk = AIMessageChunk(content="Hello world")
    assert _extract_visible_text(chunk) == "Hello world"


def test_extract_visible_text_from_block_content():
    chunk = AIMessageChunk(
        content=[
            {"type": "thinking", "thinking": "hidden"},
            {"type": "text", "text": "visible"},
        ]
    )
    assert _extract_visible_text(chunk) == "visible"


def test_extract_interrupt_travel_info():
    intr = Interrupt(
        value={
            "type": "travel_info_request",
            "missing_fields": "destination",
            "collected_data": "",
        },
        id="int-1",
    )
    events = _extract_interrupts({"__interrupt__": [intr]}, "thread-1")
    assert len(events) == 1
    assert events[0].interrupt_type == "travel_info_request"
    assert events[0].thread_id == "thread-1"


def test_extract_interrupt_approval():
    intr = Interrupt(
        value={"action_requests": [{"name": "flights_cancel", "args": {}}]},
        id="int-2",
    )
    events = _extract_interrupts({"__interrupt__": [intr]}, "thread-2")
    assert events[0].interrupt_type == "approval"


def test_sse_event_serializes():
    event = _thinking_for_tool("web_search", {"q": "hotels"}, "main")
    payload = json.loads(event.model_dump_json())
    assert payload["type"] == "thinking"
