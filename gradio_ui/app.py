"""Gradio chat UI — live process bubbles + final reply in the main chat."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import gradio as gr

from api_view.config import DEFAULT_PASSENGER_ID, DEFAULT_USER_ID, DEFAULT_USERNAME, GRADIO_HOST, GRADIO_PORT
from api_view.services.catalog_display import (
    collapse_approval_actions,
    format_approval_arg_lines,
    quantity_label,
)
from gradio_ui.client import TravelAPIClient

client = TravelAPIClient()

# Per-session state (thread_id, pending HITL interrupts)
_session: dict[str, Any] = {
    "thread_id": None,
    # One or more interrupt events awaiting resume (LangGraph may pause several at once)
    "pending_interrupts": [],
    "username": DEFAULT_USERNAME,
    "user_id": DEFAULT_USER_ID,
}

_MEMORY_JSON_TAIL = re.compile(
    r'\s*\{\s*"destinations"\s*:\s*\[.*?\]\s*,\s*"query"\s*:\s*".*?"\s*\}\s*$',
    re.DOTALL,
)

_MAX_ARGS_CHARS = 600
_MAX_RESULT_CHARS = 800

# Throttle final-answer token yields so Gradio stays responsive
_TOKEN_YIELD_EVERY = 8

_OPTION_APPROVE = "__approve__"
_OPTION_REJECT = "__reject__"


def _clean_assistant_text(text: str) -> str:
    return _MEMORY_JSON_TAIL.sub("", text or "").rstrip()


def _compact(text: Any, limit: int) -> str:
    s = " ".join(str(text or "").split())
    if len(s) > limit:
        return s[:limit] + "…"
    return s


def _pretty_payload(raw: Any, limit: int) -> str:
    """Format tool args/results as plain text; try JSON pretty-print when possible."""
    if raw is None:
        return ""
    if isinstance(raw, (dict, list)):
        try:
            text = json.dumps(raw, ensure_ascii=False, indent=2)
        except TypeError:
            text = str(raw)
    else:
        text = str(raw).strip()
        if not text or text in ("{}", "[]", "null"):
            return ""
        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            return _compact(text, limit)
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _approval_actions(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = payload or {}
    actions = payload.get("actions")
    if isinstance(actions, list) and actions:
        return [a for a in actions if isinstance(a, dict)]
    requests = payload.get("action_requests") or []
    out: list[dict[str, Any]] = []
    for req in requests:
        if isinstance(req, dict):
            out.append(
                {
                    "name": req.get("name") or req.get("tool") or "action",
                    "args": req.get("args") or {},
                }
            )
    return out


# Map internal tool names → customer-facing labels (never show raw tool ids to users)
_TOOL_ACTION_LABELS: dict[str, str] = {
    "flights_cancel": "Cancel flight ticket",
    "flights_book": "Book flight",
    "flights_update": "Change flight booking",
    "hotels_book": "Book hotel stay",
    "hotels_update": "Update hotel reservation",
    "hotels_cancel": "Cancel hotel reservation",
    "car_book": "Book car rental",
    "car_update": "Update car rental",
    "car_cancel": "Cancel car rental",
    "activity_book": "Book activity",
    "activity_update": "Update activity booking",
    "activity_cancel": "Cancel activity booking",
}


def _friendly_action_title(tool_name: str) -> str:
    key = (tool_name or "").strip()
    if key in _TOOL_ACTION_LABELS:
        return _TOOL_ACTION_LABELS[key]
    # Generic fallback without exposing snake_case tool ids
    if key.endswith("_cancel"):
        return "Cancel booking"
    if key.endswith("_book"):
        return "Create booking"
    if key.endswith("_update"):
        return "Update booking"
    return "Confirm this travel change"


def _friendly_arg_lines(
    tool_name: str,
    args: dict[str, Any],
    *,
    guest_name: str | None = None,
) -> list[str]:
    """Render approval args as customer-facing labels (names, not catalog IDs)."""
    return format_approval_arg_lines(
        tool_name,
        args,
        guest_name=guest_name or _session.get("username"),
    )

def _approval_resume_value(decision: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    """LangGraph requires one decision entry per hanging tool call."""
    n = max(1, len(_approval_actions(payload)))
    return {"decisions": [{"type": decision} for _ in range(n)]}


def _dedupe_interrupt_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per interrupt_id (stream may historically emit duplicates)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        iid = str(event.get("interrupt_id") or "").strip()
        key = iid if iid and iid != "unknown" else f"anon-{len(out)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(event)
    return out


def _pending_interrupts() -> list[dict[str, Any]]:
    raw = _session.get("pending_interrupts") or []
    return _dedupe_interrupt_events([e for e in raw if isinstance(e, dict)])


def _set_pending_interrupts(events: list[dict[str, Any]] | None) -> None:
    _session["pending_interrupts"] = _dedupe_interrupt_events(list(events or []))


def _approval_resume_payload(
    decision: str, interrupts: list[dict[str, Any]] | None
) -> Any:
    """
    Build LangGraph resume value for one or more approval interrupts.

    Multiple pending interrupts require ``{interrupt_id: decisions_payload, ...}``.
    A single interrupt may use the plain decisions payload.
    """
    events = _dedupe_interrupt_events(
        [e for e in (interrupts or []) if e.get("interrupt_type") == "approval"]
    )
    if not events:
        return {"decisions": [{"type": decision}]}

    mapped: dict[str, Any] = {}
    missing_ids = 0
    for event in events:
        iid = str(event.get("interrupt_id") or "").strip()
        value = _approval_resume_value(decision, event.get("payload"))
        if iid and iid != "unknown":
            mapped[iid] = value
        else:
            missing_ids += 1

    if len(events) > 1:
        # LangGraph requires interrupt ids when more than one is pending
        if missing_ids or len(mapped) != len(events):
            raise ValueError(
                "Multiple approvals are pending but some are missing interrupt ids."
            )
        return mapped
    if mapped:
        # Prefer id-keyed resume even for a single interrupt (forward-compatible)
        return mapped
    return _approval_resume_value(decision, events[0].get("payload"))


def _collect_approval_actions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for event in events:
        if event.get("interrupt_type") != "approval":
            continue
        actions.extend(_approval_actions(event.get("payload")))
    return actions


def _build_interrupt_reply(event: dict[str, Any]) -> dict[str, Any]:
    """Build HITL reply for a single interrupt event."""
    return _build_interrupt_reply_from_events([event])


def _build_interrupt_reply_from_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Real assistant bubble for HITL — never leave the user stranded in thinking steps.

    Merges multiple parallel approval interrupts into one confirmation.
    User-facing copy must be natural language (no tool / agent / skill names).
    """
    events = [e for e in events if isinstance(e, dict)]
    if not events:
        return {
            "role": "assistant",
            "content": (
                "I've paused and need your input to continue. "
                "Please use the Resume panel below."
            ),
        }

    approval_events = [e for e in events if e.get("interrupt_type") == "approval"]
    if approval_events:
        actions = _collect_approval_actions(approval_events)
        grouped = collapse_approval_actions(actions)
        n_raw = len(actions)
        n = len(grouped)
        lines: list[str] = []
        if n == 0:
            lines.append(
                "I need your confirmation before I make a change to your travel plans."
            )
        elif n == 1:
            item = grouped[0]
            title = _friendly_action_title(str(item.get("name") or ""))
            qty = int(item.get("quantity") or 1)
            if qty > 1:
                lines.append(f"Please confirm: **{title}** (×{qty}).")
            else:
                lines.append(f"Please confirm: **{title}**.")
            detail = _friendly_arg_lines(
                str(item.get("name") or ""),
                item.get("args") or {},
            )
            if detail:
                lines.append("")
                lines.extend(detail)
            qline = quantity_label(str(item.get("name") or ""), qty)
            if qline:
                lines.append(qline)
        else:
            header = (
                f"Please confirm the following **{n} changes**"
            )
            if n_raw > n:
                header += f" ({n_raw} reservations total)"
            header += " (approve confirms all of them; reject cancels all of them):"
            lines.append(header)
            lines.append("")
            for i, item in enumerate(grouped, start=1):
                title = _friendly_action_title(str(item.get("name") or ""))
                qty = int(item.get("quantity") or 1)
                if qty > 1:
                    lines.append(f"**{i}. {title}** (×{qty})")
                else:
                    lines.append(f"**{i}. {title}**")
                detail = _friendly_arg_lines(
                    str(item.get("name") or ""), item.get("args") or {}
                )
                lines.extend(detail)
                qline = quantity_label(str(item.get("name") or ""), qty)
                if qline:
                    lines.append(qline)
                lines.append("")
            # Warn only for multiple distinct hotel/car/activity options (not round-trip flights)
            for prefix, label in (
                ("hotels_book", "hotels"),
                ("car_book", "car rentals"),
                ("activity_book", "activities"),
            ):
                opts = [g for g in grouped if str(g.get("name") or "") == prefix]
                if len(opts) > 1:
                    lines.append(
                        f"_Note: several different {label} were prepared at once. "
                        "If you only meant to reserve one option, please Reject "
                        "and tell me which single option you prefer._"
                    )
                    lines.append("")
                    break

        lines.append("Tap **Approve** or **Reject** to continue.")
        return {
            "role": "assistant",
            "content": "\n".join(lines).rstrip(),
            "options": [
                {"value": _OPTION_APPROVE, "label": "✅ Approve"},
                {"value": _OPTION_REJECT, "label": "❌ Reject"},
            ],
        }

    # Prefer travel-info if present
    for event in events:
        if event.get("interrupt_type") == "travel_info_request":
            payload = event.get("payload") or {}
            missing = payload.get("missing_fields") or "(unspecified)"
            collected = payload.get("collected_data") or "(none yet)"
            content = (
                "I need a bit more information before I can continue.\n\n"
                f"**Still needed:** {missing}\n"
                f"**Already have:** {collected}\n\n"
                "Reply in the chat with the missing details, or use the "
                "**Resume** panel below."
            )
            return {"role": "assistant", "content": content}

    return {
        "role": "assistant",
        "content": (
            "I've paused and need your input to continue. "
            "Please use the Resume panel below."
        ),
    }


def _normalize_option_decision(value: Any) -> str | None:
    """Map chat option click / label text to approve|reject."""
    raw = value
    if isinstance(value, dict):
        raw = value.get("value") or value.get("label") or ""
    text = str(raw or "").strip()
    lowered = text.lower()
    if text in (_OPTION_APPROVE, _OPTION_REJECT):
        return "approve" if text == _OPTION_APPROVE else "reject"
    if "approve" in lowered and "reject" not in lowered:
        return "approve"
    if "reject" in lowered:
        return "reject"
    return None


def _format_process_event(event: dict[str, Any]) -> str | None:
    """Turn one SSE event into a plain-language process body (or None to skip)."""
    etype = event.get("type", "")

    if etype == "thinking":
        category = event.get("category") or ""
        meta = event.get("metadata") or {}
        content = (event.get("content") or "").strip()
        if not content:
            return None
        if category == "status" and meta.get("kind") == "agent_switch":
            # content is already "Current: …"
            label = content.removeprefix("Current:").strip()
            return f"**Current:** {label}"
        if category == "status" and meta.get("kind") == "skill":
            skill = (meta.get("skill") or "").strip()
            action = (meta.get("action") or "activate").strip()
            scope = (meta.get("scope") or "").strip()
            if action == "assign":
                agent = (meta.get("agent") or scope or "main").strip()
                label = skill or content
                return f"**Skill assign:** `{label}` → `{agent}`"
            label = skill or content.removeprefix("Skill:").strip()
            scope_bit = f" (`{scope}`)" if scope and scope != "main" else ""
            return f"**Skill:** `{label}`{scope_bit}"
        if category == "delegation":
            return f"**Handover:** {content}"
        # Skip tool/plan/reasoning thinking — covered by tool_* / plan events
        return None

    if etype == "plan":
        todos = event.get("todos") or []
        if not todos:
            return None
        lines = ["**Todo list**"]
        for t in todos:
            status = t.get("status", "?")
            content = t.get("content", "")
            lines.append(f"- [{status}] {content}")
        return "\n".join(lines)

    if etype == "tool_start":
        name = (event.get("tool_name") or "").strip()
        if not name:
            return None
        source = (event.get("source") or "").strip()
        if source.endswith("-agent"):
            return f"**Tool call** (`{source}`): `{name}`"
        return f"**Tool call:** `{name}`"

    if etype == "tool_args":
        pretty = _pretty_payload(event.get("args"), _MAX_ARGS_CHARS)
        if not pretty:
            return None
        return f"**Tool args:**\n```\n{pretty}\n```"

    if etype == "tool_result":
        name = (event.get("tool_name") or "tool").strip()
        source = (event.get("source") or "").strip()
        label = f" (`{source}`)" if source.endswith("-agent") else ""
        pretty = _pretty_payload(event.get("result"), _MAX_RESULT_CHARS)
        if not pretty:
            return f"**Tool result**{label} (`{name}`): _(empty)_"
        return f"**Tool result**{label} (`{name}`):\n```\n{pretty}\n```"

    if etype == "error":
        return f"**Error:** {event.get('message', '')}"

    # Interrupts become a real reply via _build_interrupt_reply — not a thought bubble
    return None


def _process_chat_message(body: str) -> dict[str, Any]:
    """
    Build an assistant message rendered as a Gradio 'thought' (Working…).

    Thoughts use `.thought-group` styling (muted bg + gray text via custom CSS),
    separate from the final reply bubble which stays default.
    """
    return {
        "role": "assistant",
        "content": body,
        "metadata": {"title": "Working…"},
    }


def _session_status() -> str:
    status = f"Thread: {_session.get('thread_id') or 'new'}"
    pending = _pending_interrupts()
    if pending:
        types = {e.get("interrupt_type") for e in pending}
        if "approval" in types:
            n = len(_collect_approval_actions(pending))
            status += (
                f" | ⚠️ Waiting for Approve / Reject ({n} change{'s' if n != 1 else ''})"
            )
        else:
            status += " | ⚠️ Waiting for your input"
    return status


def _hitl_visibility() -> tuple[Any, Any]:
    """Visibility for approval button row and travel-info resume hint."""
    pending = _pending_interrupts()
    is_approval = any(e.get("interrupt_type") == "approval" for e in pending)
    is_info = any(e.get("interrupt_type") == "travel_info_request" for e in pending)
    return gr.update(visible=is_approval), gr.update(visible=is_info)


def _ui_pack(
    history: list[dict],
    *,
    clear_msg: bool = True,
) -> tuple[Any, ...]:
    """Standard outputs: chatbot, status, msg, approval_row, info_row."""
    approval_vis, info_vis = _hitl_visibility()
    msg_out: Any = "" if clear_msg else gr.update()
    return history, _session_status(), msg_out, approval_vis, info_vis


def _replace_last_assistant(history: list[dict], content: str) -> list[dict]:
    """Return a new history list with the last assistant message content updated."""
    if not history or history[-1].get("role") != "assistant":
        return history + [{"role": "assistant", "content": content}]
    last = dict(history[-1])
    last["content"] = content
    # Don't attach HITL options onto a streaming final reply
    last.pop("options", None)
    return history[:-1] + [last]


def _strip_options(history: list[dict]) -> list[dict]:
    """Remove clickable options after the user has decided."""
    out: list[dict] = []
    for msg in history:
        if isinstance(msg, dict) and "options" in msg:
            cleaned = {k: v for k, v in msg.items() if k != "options"}
            out.append(cleaned)
        else:
            out.append(msg)
    return out


def _stream_turn_into_chat(
    history: list[dict],
    events: Iterator[dict[str, Any]],
) -> Iterator[tuple[Any, ...]]:
    """
    Yield live chat updates from an SSE event iterator.

    Each process step becomes its own assistant bubble; the final answer is a
    separate bubble. Interrupts always produce a real reply (with Approve/Reject
    options when needed).
    """
    seen: set[str] = set()
    saw_interrupt = False
    interrupt_events: list[dict[str, Any]] = []
    final_started = False
    final_text = ""
    token_since_yield = 0

    for event in events:
        etype = event.get("type", "")
        line = _format_process_event(event)

        if line and (etype == "plan" or line not in seen):
            if etype != "plan":
                seen.add(line)
            # Mid-turn model narration before more tools must not stay as a
            # chat bubble — drop it; only the final deliverable is kept.
            if final_started:
                if (
                    history
                    and history[-1].get("role") == "assistant"
                    and "options" not in history[-1]
                ):
                    history = history[:-1]
                final_started = False
                final_text = ""
                token_since_yield = 0
            history = history + [_process_chat_message(line)]
            yield _ui_pack(history)

        if etype == "token":
            chunk = event.get("content", "")
            if not chunk:
                continue
            if not final_started:
                history = history + [{"role": "assistant", "content": ""}]
                final_started = True
                final_text = ""
                token_since_yield = 0
            final_text += chunk
            token_since_yield += 1
            history = _replace_last_assistant(history, final_text)
            if token_since_yield >= _TOKEN_YIELD_EVERY:
                token_since_yield = 0
                yield _ui_pack(history)

        elif etype == "done":
            _session["thread_id"] = event.get("thread_id") or _session.get("thread_id")
            done_content = event.get("content") or ""
            if done_content and not final_text.strip():
                if not final_started:
                    history = history + [{"role": "assistant", "content": ""}]
                    final_started = True
                final_text = done_content
                history = _replace_last_assistant(history, final_text)

        elif etype == "interrupt":
            saw_interrupt = True
            interrupt_events.append(event)
            interrupt_events = _dedupe_interrupt_events(interrupt_events)
            _set_pending_interrupts(interrupt_events)
            # Surface Approve/Reject as soon as HITL pauses (don't wait for done)
            if final_started and not (final_text or "").strip():
                if (
                    history
                    and history[-1].get("role") == "assistant"
                    and "options" not in history[-1]
                ):
                    history = history[:-1]
                final_started = False
                final_text = ""
            # Replace prior HITL option bubble from this turn if we re-merge
            if (
                history
                and history[-1].get("role") == "assistant"
                and "options" in history[-1]
            ):
                history = history[:-1]
            history = history + [_build_interrupt_reply_from_events(interrupt_events)]
            yield _ui_pack(history)

        elif etype == "error":
            msg = f"Error: {event.get('message', '')}"
            if not final_started:
                history = history + [
                    _process_chat_message(f"**Error:** {event.get('message', '')}")
                ]
            else:
                final_text = msg
                history = _replace_last_assistant(history, final_text)
            yield _ui_pack(history)

    if not saw_interrupt:
        _set_pending_interrupts([])

    if final_started:
        history = _replace_last_assistant(
            history, _clean_assistant_text(final_text) or final_text
        )

    # Always close interrupts with a real assistant reply (+ Approve/Reject).
    # Skip if we already attached the HITL bubble when the interrupt arrived.
    if interrupt_events:
        if not (
            history
            and history[-1].get("role") == "assistant"
            and "options" in history[-1]
        ):
            history = history + [_build_interrupt_reply_from_events(interrupt_events)]

    yield _ui_pack(history)


def _remember_user(user_id: str, username: str) -> None:
    if user_id:
        _session["user_id"] = user_id
    if username:
        _session["username"] = username


def _process_stream_events(
    message: str,
    history: list[dict],
    user_id: str,
    username: str,
    passenger_id: str,
) -> Iterator[tuple[Any, ...]]:
    """Live-update the chat: user bubble first, then process bubbles, then final reply."""
    _remember_user(user_id, username)
    history = list(history or []) + [{"role": "user", "content": message}]
    yield _ui_pack(history)

    thread_id = _session.get("thread_id")
    try:
        events = client.stream_chat(
            message,
            thread_id,
            user_id=user_id,
            username=username,
            passenger_id=passenger_id,
        )
        yield from _stream_turn_into_chat(history, events)
    except Exception as exc:
        history = history + [_process_chat_message(f"**Error:** {exc}")]
        yield _ui_pack(history)


def _resume_interrupt(
    resume_text: str,
    history: list[dict],
    user_id: str,
    username: str,
    passenger_id: str,
    *,
    decision: str | None = None,
) -> Iterator[tuple[Any, ...]]:
    """
    Resume after HITL.

    ``decision`` is ``"approve"`` / ``"reject"`` for approval interrupts.
    Otherwise ``resume_text`` is sent (travel-info / free-form).
    """
    _remember_user(user_id, username)
    thread_id = _session.get("thread_id")
    history = _strip_options(list(history or []))
    if not thread_id:
        yield history, "No active thread", gr.update(), *_hitl_visibility()
        return

    interrupts = _pending_interrupts()
    approval_events = [e for e in interrupts if e.get("interrupt_type") == "approval"]
    info_events = [
        e for e in interrupts if e.get("interrupt_type") == "travel_info_request"
    ]

    if approval_events:
        if decision not in ("approve", "reject"):
            yield (
                history,
                "Use Approve or Reject for this action.",
                gr.update(),
                *_hitl_visibility(),
            )
            return
        try:
            resume_value: Any = _approval_resume_payload(decision, approval_events)
        except ValueError as exc:
            yield (
                history,
                str(exc),
                gr.update(),
                *_hitl_visibility(),
            )
            return
        resume_label = decision
    else:
        if not (resume_text or "").strip():
            yield (
                history,
                "Enter the missing travel details to resume.",
                gr.update(),
                *_hitl_visibility(),
            )
            return
        # Travel-info: map by interrupt id when multiple are pending
        if len(info_events) > 1:
            resume_value = {
                str(e.get("interrupt_id")): resume_text
                for e in info_events
                if e.get("interrupt_id")
            }
        elif len(info_events) == 1 and info_events[0].get("interrupt_id"):
            resume_value = {str(info_events[0]["interrupt_id"]): resume_text}
        else:
            resume_value = resume_text
        resume_label = resume_text

    history = history + [{"role": "user", "content": f"[Resume] {resume_label}"}]
    # Clear pending before stream so the bar hides until a new interrupt
    _set_pending_interrupts([])
    yield _ui_pack(history)

    try:
        events = client.stream_resume(
            thread_id,
            resume_value,
            user_id=user_id,
            username=username,
            passenger_id=passenger_id,
        )
        yield from _stream_turn_into_chat(history, events)
    except Exception as exc:
        history = history + [_process_chat_message(f"**Error:** {exc}")]
        yield _ui_pack(history)


def _on_option_select(
    history: list[dict],
    user_id: str,
    username: str,
    passenger_id: str,
    evt: gr.SelectData,
) -> Iterator[tuple[Any, ...]]:
    """Handle in-chat Approve / Reject option clicks."""
    value = getattr(evt, "value", None)
    decision = _normalize_option_decision(value)
    if decision in ("approve", "reject"):
        yield from _resume_interrupt(
            "", history, user_id, username, passenger_id, decision=decision
        )
        return
    # Treat other option values as free-form resume text
    yield from _resume_interrupt(
        str(value or ""), history, user_id, username, passenger_id, decision=None
    )


def _new_conversation() -> tuple[Any, ...]:
    _session["thread_id"] = None
    _set_pending_interrupts([])
    return [], "New conversation started", "", *_hitl_visibility()


def _check_agent_status() -> str:
    try:
        status = client.agent_status()
        return json.dumps(status, indent=2)
    except Exception as exc:
        return f"API unreachable: {exc}\n\nStart the API with: python -m api_view.run"


def _init_agent() -> str:
    try:
        result = client.initialize_agent()
        return json.dumps(result, indent=2)
    except Exception as exc:
        return f"Init failed: {exc}"


# Muted styling for process/thought bubbles only — final replies keep Gradio defaults
_PROCESS_BUBBLE_CSS = """
#travel-chatbot .thought-group {
  background: #eef1f5 !important;
  border: 1px solid #d8dee6 !important;
  border-radius: 10px !important;
  color: #6b7280 !important;
}
#travel-chatbot .thought-group .message-content,
#travel-chatbot .thought-group .message-content p,
#travel-chatbot .thought-group .message-content li,
#travel-chatbot .thought-group .message-content strong,
#travel-chatbot .thought-group .message-content em,
#travel-chatbot .thought-group button,
#travel-chatbot .thought-group summary,
#travel-chatbot .thought-group .thought {
  color: #6b7280 !important;
}
#travel-chatbot .thought-group .message-content {
  opacity: 0.92;
}
#travel-chatbot .thought-group code,
#travel-chatbot .thought-group pre {
  color: #6b7280 !important;
  background: #e4e8ee !important;
  border-color: #d0d5dd !important;
}
#hitl-approval-bar {
  border: 1px solid #f0c36d;
  background: #fff8e8;
  border-radius: 10px;
  padding: 10px 12px;
  margin-top: 4px;
}
#hitl-info-bar {
  border: 1px solid #93c5fd;
  background: #eff6ff;
  border-radius: 10px;
  padding: 10px 12px;
  margin-top: 4px;
}
"""


def _gradio_approve(
    history: list[dict],
    user_id: str,
    username: str,
    passenger_id: str,
) -> Iterator[tuple[Any, ...]]:
    yield from _resume_interrupt(
        "", history, user_id, username, passenger_id, decision="approve"
    )


def _gradio_reject(
    history: list[dict],
    user_id: str,
    username: str,
    passenger_id: str,
) -> Iterator[tuple[Any, ...]]:
    yield from _resume_interrupt(
        "", history, user_id, username, passenger_id, decision="reject"
    )


def _gradio_resume_submit(
    resume_text: str,
    history: list[dict],
    user_id: str,
    username: str,
    passenger_id: str,
) -> Iterator[tuple[Any, ...]]:
    yield from _resume_interrupt(
        resume_text, history, user_id, username, passenger_id, decision=None
    )


def create_app() -> gr.Blocks:
    with gr.Blocks(title="AI Travel Assistant") as demo:
        gr.Markdown(
            "# ✈️ AI Travel Assistant\n"
            "Under-the-hood steps appear as muted bubbles; the assistant always "
            "ends with a real reply. Sensitive actions show **Approve / Reject** "
            "in the chat."
        )

        chatbot = gr.Chatbot(
            label="Chat",
            height=560,
            buttons=["copy"],
            group_consecutive_messages=False,
            elem_id="travel-chatbot",
        )
        msg = gr.Textbox(
            label="Your message",
            placeholder="e.g. Book a hotel in Paris between 26 and 28 July",
            lines=2,
        )
        with gr.Row():
            send_btn = gr.Button("Send", variant="primary")
            new_btn = gr.Button("New Conversation")
        status_bar = gr.Textbox(label="Session", interactive=False)

        with gr.Group(visible=False, elem_id="hitl-approval-bar") as approval_row:
            gr.Markdown(
                "**Action approval required** — confirm or reject the pending operation."
            )
            with gr.Row():
                approve_btn = gr.Button("Approve", variant="primary")
                reject_btn = gr.Button("Reject", variant="stop")

        with gr.Group(visible=False, elem_id="hitl-info-bar") as info_row:
            gr.Markdown(
                "**More information needed** — reply in the chat, or enter details below and click Resume."
            )
            resume_input = gr.Textbox(
                label="Resume data",
                placeholder="e.g. destination=Paris, check_in=2026-07-26",
                lines=2,
            )
            resume_btn = gr.Button("Resume with text", variant="secondary")

        with gr.Accordion("Agent Lifecycle", open=False):
            agent_status = gr.Textbox(label="Agent Status", lines=4, interactive=False)
            with gr.Row():
                status_btn = gr.Button("Check Status")
                init_btn = gr.Button("Initialize Agent", variant="secondary")

        with gr.Accordion("User Settings", open=False):
            with gr.Row():
                user_id = gr.Textbox(label="User ID", value=DEFAULT_USER_ID)
                username = gr.Textbox(label="Username", value=DEFAULT_USERNAME)
                passenger_id = gr.Textbox(
                    label="Passenger ID (= User ID for flights)",
                    value=DEFAULT_PASSENGER_ID,
                )

        chat_outputs = [chatbot, status_bar, msg, approval_row, info_row]

        send_btn.click(
            _process_stream_events,
            inputs=[msg, chatbot, user_id, username, passenger_id],
            outputs=chat_outputs,
        )
        msg.submit(
            _process_stream_events,
            inputs=[msg, chatbot, user_id, username, passenger_id],
            outputs=chat_outputs,
        )
        new_btn.click(_new_conversation, outputs=chat_outputs)
        status_btn.click(_check_agent_status, outputs=[agent_status])
        init_btn.click(_init_agent, outputs=[agent_status])

        chatbot.option_select(
            _on_option_select,
            inputs=[chatbot, user_id, username, passenger_id],
            outputs=chat_outputs,
        )

        # Module-level generators (not lambdas / nested fns): Gradio must iterate
        # yields of 5 outputs; returning a generator object counts as 1 value.
        approve_btn.click(
            _gradio_approve,
            inputs=[chatbot, user_id, username, passenger_id],
            outputs=chat_outputs,
        )
        reject_btn.click(
            _gradio_reject,
            inputs=[chatbot, user_id, username, passenger_id],
            outputs=chat_outputs,
        )
        resume_btn.click(
            _gradio_resume_submit,
            inputs=[resume_input, chatbot, user_id, username, passenger_id],
            outputs=chat_outputs,
        )

        demo.load(_check_agent_status, outputs=[agent_status])

    return demo


def main():
    app = create_app()
    simple_font = (gr.themes.Font("Calibri"), "Arial", "Helvetica", "sans-serif")
    simple_mono = (gr.themes.Font("Consolas"), "Menlo", "Courier New", "monospace")
    app.launch(
        server_name=GRADIO_HOST,
        server_port=GRADIO_PORT,
        share=False,
        theme=gr.themes.Soft(font=simple_font, font_mono=simple_mono),
        css=_PROCESS_BUBBLE_CSS,
    )


if __name__ == "__main__":
    main()
