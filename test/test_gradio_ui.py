"""Tests for Gradio UI helpers."""

from gradio_ui.app import (
    _OPTION_APPROVE,
    _OPTION_REJECT,
    _approval_actions,
    _approval_resume_value,
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


def test_format_skill_thinking():
    text = _format_process_event(
        {
            "type": "thinking",
            "category": "status",
            "content": "Skill: compound-travel-package",
            "metadata": {
                "kind": "skill",
                "skill": "compound-travel-package",
                "scope": "main",
                "action": "activate",
            },
        }
    )
    assert text == "**Skill:** `compound-travel-package`"


def test_format_skill_assign_thinking():
    text = _format_process_event(
        {
            "type": "thinking",
            "category": "status",
            "content": "Assign skill: web-fetcher → hotels-agent",
            "metadata": {
                "kind": "skill",
                "skill": "web-fetcher",
                "action": "assign",
                "agent": "hotels-agent",
            },
        }
    )
    assert "**Skill assign:**" in text
    assert "web-fetcher" in text
    assert "hotels-agent" in text


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
                        "args": {
                            "hotel_id": 1,
                            "user_id": "3442 587242",
                            "checkin_date": "2026-07-24",
                            "checkout_date": "2026-07-28",
                        },
                    }
                ]
            },
        }
    )
    assert reply["role"] == "assistant"
    # Must be natural language — never expose tool names
    assert "hotels_book" not in reply["content"]
    assert "Book hotel stay" in reply["content"]
    assert "Check-in" in reply["content"]
    assert "Approve" in reply["content"] or "approve" in reply["content"].lower()
    values = {o["value"] for o in reply["options"]}
    assert values == {_OPTION_APPROVE, _OPTION_REJECT}


def test_build_approval_interrupt_reply_no_tool_names_for_cancel():
    reply = _build_interrupt_reply(
        {
            "interrupt_type": "approval",
            "payload": {
                "actions": [
                    {
                        "name": "flights_cancel",
                        "args": {
                            "ticket_no": "7240005432906569",
                            "passenger_id": "3442 587242",
                        },
                    }
                ]
            },
        }
    )
    assert "flights_cancel" not in reply["content"]
    assert "Cancel flight ticket" in reply["content"]
    assert "Ticket number" in reply["content"]
    assert "7240005432906569" in reply["content"]


def test_approval_resume_value_expands_to_all_actions():
    payload = {
        "actions": [
            {"name": "hotels_book", "args": {"hotel_id": 2}},
            {"name": "hotels_book", "args": {"hotel_id": 7}},
            {"name": "hotels_book", "args": {"hotel_id": 9}},
        ]
    }
    value = _approval_resume_value("approve", payload)
    assert value == {
        "decisions": [{"type": "approve"}, {"type": "approve"}, {"type": "approve"}]
    }
    reject = _approval_resume_value("reject", payload)
    assert len(reject["decisions"]) == 3
    assert all(d["type"] == "reject" for d in reject["decisions"])


def test_approval_resume_value_single_action():
    value = _approval_resume_value(
        "approve", {"actions": [{"name": "flights_cancel", "args": {}}]}
    )
    assert value == {"decisions": [{"type": "approve"}]}


def test_build_multi_approval_interrupt_warns_when_many_books():
    reply = _build_interrupt_reply(
        {
            "interrupt_type": "approval",
            "payload": {
                "actions": [
                    {
                        "name": "hotels_book",
                        "args": {"hotel_id": 2, "checkin_date": "2026-07-24"},
                    },
                    {
                        "name": "hotels_book",
                        "args": {"hotel_id": 7, "checkin_date": "2026-07-24"},
                    },
                    {
                        "name": "hotels_book",
                        "args": {"hotel_id": 9, "checkin_date": "2026-07-24"},
                    },
                ]
            },
        }
    )
    assert "hotels_book" not in reply["content"]
    assert "3 changes" in reply["content"]
    assert "Reject" in reply["content"]
    assert "only meant to reserve one" in reply["content"].lower()


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
