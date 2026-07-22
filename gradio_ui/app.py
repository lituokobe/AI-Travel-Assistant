"""Gradio chat UI — live process bubbles + final reply in the main chat."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import gradio as gr

from api_view.config import DEFAULT_PASSENGER_ID, DEFAULT_USER_ID, DEFAULT_USERNAME, GRADIO_HOST, GRADIO_PORT
from gradio_ui.client import TravelAPIClient

client = TravelAPIClient()

# Per-session state (thread_id, pending_interrupt)
_session: dict[str, Any] = {
    "thread_id": None,
    "pending_interrupt": None,
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


def _build_interrupt_reply(event: dict[str, Any]) -> dict[str, Any]:
    """
    Real assistant bubble for HITL — never leave the user stranded in thinking steps.

    Approval interrupts include in-chat Approve / Reject options.
    """
    itype = event.get("interrupt_type") or "interrupt"
    payload = event.get("payload") or {}

    if itype == "approval":
        actions = _approval_actions(payload)
        lines = [
            "I need your approval before I continue with this action.",
            "",
        ]
        if not actions:
            lines.append("A sensitive operation is waiting for your decision.")
        for i, action in enumerate(actions, start=1):
            name = action.get("name") or "action"
            args = action.get("args") or {}
            prefix = f"**Action {i}:**" if len(actions) > 1 else "**Action:**"
            lines.append(f"{prefix} `{name}`")
            pretty = _pretty_payload(args, _MAX_ARGS_CHARS)
            if pretty:
                lines.append("**Details:**")
                lines.append(f"```\n{pretty}\n```")
            lines.append("")
        lines.append("Please **Approve** or **Reject** to continue.")
        return {
            "role": "assistant",
            "content": "\n".join(lines).rstrip(),
            "options": [
                {"value": _OPTION_APPROVE, "label": "✅ Approve"},
                {"value": _OPTION_REJECT, "label": "❌ Reject"},
            ],
        }

    if itype == "travel_info_request":
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
    pending = _session.get("pending_interrupt")
    if pending:
        itype = pending.get("interrupt_type") or "interrupt"
        if itype == "approval":
            status += " | ⚠️ Waiting for Approve / Reject"
        else:
            status += " | ⚠️ Waiting for your input"
    return status


def _hitl_visibility() -> tuple[Any, Any]:
    """Visibility for approval button row and travel-info resume hint."""
    pending = _session.get("pending_interrupt")
    is_approval = bool(pending and pending.get("interrupt_type") == "approval")
    is_info = bool(
        pending and pending.get("interrupt_type") == "travel_info_request"
    )
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
    interrupt_event: dict[str, Any] | None = None
    final_started = False
    final_text = ""
    token_since_yield = 0

    for event in events:
        etype = event.get("type", "")
        line = _format_process_event(event)

        if line and (etype == "plan" or line not in seen):
            if etype != "plan":
                seen.add(line)
            if final_started:
                cleaned = _clean_assistant_text(final_text)
                history = _replace_last_assistant(history, cleaned or final_text)
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
            interrupt_event = event
            _session["pending_interrupt"] = event

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
        _session["pending_interrupt"] = None

    if final_started:
        history = _replace_last_assistant(
            history, _clean_assistant_text(final_text) or final_text
        )

    # Always close an interrupt with a real assistant reply (+ Approve/Reject)
    if interrupt_event is not None:
        history = history + [_build_interrupt_reply(interrupt_event)]

    yield _ui_pack(history)


def _process_stream_events(
    message: str,
    history: list[dict],
    user_id: str,
    username: str,
    passenger_id: str,
) -> Iterator[tuple[Any, ...]]:
    """Live-update the chat: user bubble first, then process bubbles, then final reply."""
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
    thread_id = _session.get("thread_id")
    history = _strip_options(list(history or []))
    if not thread_id:
        yield history, "No active thread", gr.update(), *_hitl_visibility()
        return

    interrupt = _session.get("pending_interrupt")
    itype = (interrupt or {}).get("interrupt_type")

    if itype == "approval":
        if decision not in ("approve", "reject"):
            yield (
                history,
                "Use Approve or Reject for this action.",
                gr.update(),
                *_hitl_visibility(),
            )
            return
        resume_value: Any = {"decisions": [{"type": decision}]}
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
        resume_value = resume_text
        resume_label = resume_text

    history = history + [{"role": "user", "content": f"[Resume] {resume_label}"}]
    # Clear pending before stream so the bar hides until a new interrupt
    _session["pending_interrupt"] = None
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
    value = getattr(evt, "value", None) or ""
    if value == _OPTION_APPROVE:
        yield from _resume_interrupt(
            "", history, user_id, username, passenger_id, decision="approve"
        )
    elif value == _OPTION_REJECT:
        yield from _resume_interrupt(
            "", history, user_id, username, passenger_id, decision="reject"
        )
    else:
        # Treat other option values as free-form resume text
        yield from _resume_interrupt(
            str(value), history, user_id, username, passenger_id, decision=None
        )


def _new_conversation() -> tuple[Any, ...]:
    _session["thread_id"] = None
    _session["pending_interrupt"] = None
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

        approve_btn.click(
            lambda h, uid, un, pid: _resume_interrupt(
                "", h, uid, un, pid, decision="approve"
            ),
            inputs=[chatbot, user_id, username, passenger_id],
            outputs=chat_outputs,
        )
        reject_btn.click(
            lambda h, uid, un, pid: _resume_interrupt(
                "", h, uid, un, pid, decision="reject"
            ),
            inputs=[chatbot, user_id, username, passenger_id],
            outputs=chat_outputs,
        )
        resume_btn.click(
            lambda t, h, uid, un, pid: _resume_interrupt(
                t, h, uid, un, pid, decision=None
            ),
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
