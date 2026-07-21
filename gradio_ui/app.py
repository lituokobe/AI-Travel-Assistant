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


def _format_process_event(event: dict[str, Any]) -> str | None:
    """Turn one SSE event into a plain-language process body (or None to skip)."""
    etype = event.get("type", "")

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
        return f"**Tool call:** `{name}`"

    if etype == "tool_args":
        pretty = _pretty_payload(event.get("args"), _MAX_ARGS_CHARS)
        if not pretty:
            return None
        return f"**Tool args:**\n```\n{pretty}\n```"

    if etype == "tool_result":
        name = (event.get("tool_name") or "tool").strip()
        pretty = _pretty_payload(event.get("result"), _MAX_RESULT_CHARS)
        if not pretty:
            return f"**Tool result** (`{name}`): _(empty)_"
        return f"**Tool result** (`{name}`):\n```\n{pretty}\n```"

    if etype == "interrupt":
        itype = event.get("interrupt_type", "interrupt")
        return (
            f"**Paused for your input** ({itype}). "
            "Use the Resume panel below to continue."
        )

    if etype == "error":
        return f"**Error:** {event.get('message', '')}"

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
    if _session.get("pending_interrupt"):
        status += " | ⚠️ Waiting for your input (see Resume panel)"
    return status


def _replace_last_assistant(history: list[dict], content: str) -> list[dict]:
    """Return a new history list with the last assistant message content updated."""
    if not history or history[-1].get("role") != "assistant":
        return history + [{"role": "assistant", "content": content}]
    return history[:-1] + [{"role": "assistant", "content": content}]


def _stream_turn_into_chat(
    history: list[dict],
    events: Iterator[dict[str, Any]],
) -> Iterator[tuple[list[dict], str, str]]:
    """
    Yield live chat updates from an SSE event iterator.

    Each process step becomes its own assistant bubble; the final answer is a
    separate bubble that streams token-by-token.
    """
    seen: set[str] = set()
    saw_interrupt = False
    final_started = False
    final_text = ""
    token_since_yield = 0

    for event in events:
        etype = event.get("type", "")
        line = _format_process_event(event)

        if line and (etype == "plan" or line not in seen):
            if etype != "plan":
                seen.add(line)
            # Close any in-progress final bubble before more process steps
            if final_started:
                cleaned = _clean_assistant_text(final_text)
                history = _replace_last_assistant(history, cleaned or final_text)
                final_started = False
                final_text = ""
                token_since_yield = 0
            history = history + [_process_chat_message(line)]
            yield history, _session_status(), ""

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
                yield history, _session_status(), ""

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
            yield history, _session_status(), ""

    if not saw_interrupt:
        _session["pending_interrupt"] = None

    if final_started:
        history = _replace_last_assistant(
            history, _clean_assistant_text(final_text) or final_text
        )

    yield history, _session_status(), ""


def _process_stream_events(
    message: str,
    history: list[dict],
    user_id: str,
    username: str,
    passenger_id: str,
) -> Iterator[tuple[list[dict], str, str]]:
    """Live-update the chat: user bubble first, then process bubbles, then final reply."""
    history = list(history or []) + [{"role": "user", "content": message}]
    # Show the user message immediately and clear the input box
    yield history, _session_status(), ""

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
        yield history, _session_status(), ""


def _resume_interrupt(
    resume_text: str,
    history: list[dict],
    user_id: str,
    username: str,
    passenger_id: str,
    approve: bool = False,
) -> Iterator[tuple[list[dict], str]]:
    thread_id = _session.get("thread_id")
    history = list(history or [])
    if not thread_id:
        yield history, "No active thread"
        return

    interrupt = _session.get("pending_interrupt")
    if interrupt and interrupt.get("interrupt_type") == "approval":
        resume_value = {"decisions": [{"type": "approve" if approve else "reject"}]}
        resume_label = "approve" if approve else "reject"
    else:
        resume_value = resume_text
        resume_label = resume_text

    history = history + [{"role": "user", "content": f"[Resume] {resume_label}"}]
    yield history, _session_status()

    try:
        events = client.stream_resume(
            thread_id,
            resume_value,
            user_id=user_id,
            username=username,
            passenger_id=passenger_id,
        )
        for hist, status, _cleared in _stream_turn_into_chat(history, events):
            yield hist, status
    except Exception as exc:
        history = history + [_process_chat_message(f"**Error:** {exc}")]
        yield history, _session_status()


def _new_conversation() -> tuple[list, str, str]:
    _session["thread_id"] = None
    _session["pending_interrupt"] = None
    return [], "New conversation started", ""


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
"""


def create_app() -> gr.Blocks:
    with gr.Blocks(title="AI Travel Assistant") as demo:
        gr.Markdown(
            "# ✈️ AI Travel Assistant\n"
            "Each under-the-hood step (todo list, tool call, tool result) appears as its "
            "own chat bubble in real time, followed by the assistant’s final reply."
        )

        chatbot = gr.Chatbot(
            label="Chat",
            height=560,
            buttons=["copy"],
            # Keep process steps as separate bubbles (don't merge consecutive assistants)
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

        with gr.Accordion("Resume Interrupt (HITL)", open=False):
            gr.Markdown(
                "When the agent pauses for missing travel info, enter the data here. "
                "For approval interrupts (book/cancel), use Approve/Reject."
            )
            resume_input = gr.Textbox(
                label="Resume data",
                placeholder="e.g. ticket_no=123456, new_flight_id=42",
                lines=2,
            )
            with gr.Row():
                resume_btn = gr.Button("Resume with text")
                approve_btn = gr.Button("Approve", variant="primary")
                reject_btn = gr.Button("Reject", variant="stop")

        send_btn.click(
            _process_stream_events,
            inputs=[msg, chatbot, user_id, username, passenger_id],
            outputs=[chatbot, status_bar, msg],
        )
        msg.submit(
            _process_stream_events,
            inputs=[msg, chatbot, user_id, username, passenger_id],
            outputs=[chatbot, status_bar, msg],
        )
        new_btn.click(_new_conversation, outputs=[chatbot, status_bar, msg])
        status_btn.click(_check_agent_status, outputs=[agent_status])
        init_btn.click(_init_agent, outputs=[agent_status])

        resume_btn.click(
            lambda t, h, uid, un, pid: _resume_interrupt(
                t, h, uid, un, pid, approve=False
            ),
            inputs=[resume_input, chatbot, user_id, username, passenger_id],
            outputs=[chatbot, status_bar],
        )
        approve_btn.click(
            lambda t, h, uid, un, pid: _resume_interrupt(
                t, h, uid, un, pid, approve=True
            ),
            inputs=[resume_input, chatbot, user_id, username, passenger_id],
            outputs=[chatbot, status_bar],
        )
        reject_btn.click(
            lambda t, h, uid, un, pid: _resume_interrupt(
                t, h, uid, un, pid, approve=False
            ),
            inputs=[resume_input, chatbot, user_id, username, passenger_id],
            outputs=[chatbot, status_bar],
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
