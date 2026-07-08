"""Gradio chat UI with agent thinking/planning debug panel."""

from __future__ import annotations

import json
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


def _format_thinking_event(event: dict[str, Any]) -> str:
    etype = event.get("type", "")
    if etype == "thinking":
        cat = event.get("category", "status")
        source = event.get("source", "main")
        prefix = "💭" if cat == "reasoning" else "🔧"
        return f"{prefix} [{cat.upper()}|{source}] {event.get('content', '')}"
    if etype == "reasoning":
        source = event.get("source", "main")
        return f"💭 [REASONING|{source}] {event.get('content', '')}"
    if etype == "plan":
        todos = event.get("todos", [])
        lines = [f"  • [{t.get('status', '?')}] {t.get('content', '')}" for t in todos]
        return "[PLAN]\n" + "\n".join(lines)
    if etype == "tool_start":
        return f"[TOOL] Starting: {event.get('tool_name')} (source={event.get('source', 'main')})"
    if etype == "tool_args":
        return f"[TOOL ARGS] {event.get('args', '')[:500]}"
    if etype == "tool_result":
        preview = event.get("result", "")[:300]
        return f"[TOOL RESULT] {event.get('tool_name')}: {preview}..."
    if etype == "interrupt":
        return f"[INTERRUPT] {event.get('interrupt_type')}: {json.dumps(event.get('payload', {}), ensure_ascii=False)[:500]}"
    if etype == "error":
        return f"[ERROR] {event.get('message', '')}"
    return ""


def _process_stream_events(
    message: str,
    history: list[dict],
    thinking_log: str,
    user_id: str,
    username: str,
    passenger_id: str,
) -> tuple[list[dict], str, str, str]:
    """Stream chat and accumulate thinking log."""
    thread_id = _session.get("thread_id")
    thinking_lines: list[str] = []
    assistant_text = ""

    history = history + [{"role": "user", "content": message}]

    try:
        for event in client.stream_chat(
            message,
            thread_id,
            user_id=user_id,
            username=username,
            passenger_id=passenger_id,
        ):
            etype = event.get("type", "")
            formatted = _format_thinking_event(event)
            if formatted:
                thinking_lines.append(formatted)

            if etype == "token":
                assistant_text += event.get("content", "")
            elif etype == "done":
                _session["thread_id"] = event.get("thread_id", thread_id)
            elif etype == "interrupt":
                _session["pending_interrupt"] = event
                thinking_lines.append(
                    "\n⚠️ Agent paused — use the Resume panel below to continue."
                )

    except Exception as exc:
        thinking_lines.append(f"[ERROR] {exc}")
        assistant_text = f"Error: {exc}"

    if assistant_text:
        history = history + [{"role": "assistant", "content": assistant_text}]

    new_thinking = thinking_log
    if thinking_lines:
        block = "\n".join(thinking_lines)
        new_thinking = (thinking_log + "\n\n" + block).strip() if thinking_log else block

    status = f"Thread: {_session.get('thread_id') or 'new'}"
    if _session.get("pending_interrupt"):
        status += " | ⚠️ INTERRUPT PENDING"

    return history, new_thinking, status, ""


def _resume_interrupt(
    resume_text: str,
    history: list[dict],
    thinking_log: str,
    user_id: str,
    username: str,
    passenger_id: str,
    approve: bool = False,
) -> tuple[list[dict], str, str]:
    thread_id = _session.get("thread_id")
    if not thread_id:
        return history, thinking_log, "No active thread"

    interrupt = _session.get("pending_interrupt")
    if interrupt and interrupt.get("interrupt_type") == "approval":
        resume_value = {"decisions": [{"type": "approve" if approve else "reject"}]}
    else:
        resume_value = resume_text

    thinking_lines: list[str] = [f"[RESUME] {json.dumps(resume_value, ensure_ascii=False)[:200]}"]
    assistant_text = ""

    try:
        for event in client.stream_resume(
            thread_id,
            resume_value,
            user_id=user_id,
            username=username,
            passenger_id=passenger_id,
        ):
            formatted = _format_thinking_event(event)
            if formatted:
                thinking_lines.append(formatted)
            if event.get("type") == "token":
                assistant_text += event.get("content", "")
            elif event.get("type") == "interrupt":
                _session["pending_interrupt"] = event
            elif event.get("type") == "done":
                _session["pending_interrupt"] = None
    except Exception as exc:
        thinking_lines.append(f"[ERROR] {exc}")
        assistant_text = f"Resume error: {exc}"

    if assistant_text:
        history = history + [{"role": "assistant", "content": assistant_text}]

    new_thinking = (thinking_log + "\n\n" + "\n".join(thinking_lines)).strip()
    status = f"Thread: {thread_id}"
    return history, new_thinking, status


def _new_conversation() -> tuple[list, str, str, str]:
    _session["thread_id"] = None
    _session["pending_interrupt"] = None
    return [], "", "New conversation started", ""


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


def create_app() -> gr.Blocks:
    with gr.Blocks(title="AI Travel Assistant") as demo:
        gr.Markdown(
            "# ✈️ AI Travel Assistant\n"
            "Chat with the travel concierge agent. The **Thinking Process** panel shows "
            "autonomous planning, sub-agent delegation, and tool calls for debugging."
        )

        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(
                    label="Chat",
                    height=480,
                )
                msg = gr.Textbox(
                    label="Your message",
                    placeholder="e.g. Search flights from SFO to JFK next week",
                    lines=2,
                )
                with gr.Row():
                    send_btn = gr.Button("Send", variant="primary")
                    new_btn = gr.Button("New Conversation")
                status_bar = gr.Textbox(label="Session", interactive=False)

            with gr.Column(scale=1):
                thinking_panel = gr.Textbox(
                    label="🧠 Thinking Process (debug)",
                    lines=28,
                    max_lines=50,
                    interactive=False,
                    elem_classes=["thinking-panel"],
                )
                gr.Markdown("### Agent Lifecycle")
                agent_status = gr.Textbox(label="Agent Status", lines=4, interactive=False)
                with gr.Row():
                    status_btn = gr.Button("Check Status")
                    init_btn = gr.Button("Initialize Agent", variant="secondary")

        with gr.Accordion("User Settings", open=False):
            with gr.Row():
                user_id = gr.Textbox(label="User ID", value=DEFAULT_USER_ID)
                username = gr.Textbox(label="Username", value=DEFAULT_USERNAME)
                passenger_id = gr.Textbox(label="Passenger ID", value=DEFAULT_PASSENGER_ID)

        with gr.Accordion("Resume Interrupt (HITL)", open=False):
            gr.Markdown(
                "When the agent pauses for missing travel info, enter the data here. "
                "For approval interrupts (book/cancel), use Approve/Reject buttons."
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
            inputs=[msg, chatbot, thinking_panel, user_id, username, passenger_id],
            outputs=[chatbot, thinking_panel, status_bar, msg],
        )
        msg.submit(
            _process_stream_events,
            inputs=[msg, chatbot, thinking_panel, user_id, username, passenger_id],
            outputs=[chatbot, thinking_panel, status_bar, msg],
        )
        new_btn.click(_new_conversation, outputs=[chatbot, thinking_panel, status_bar, msg])
        status_btn.click(_check_agent_status, outputs=[agent_status])
        init_btn.click(_init_agent, outputs=[agent_status])

        resume_btn.click(
            lambda t, h, th, uid, un, pid: _resume_interrupt(t, h, th, uid, un, pid, approve=False),
            inputs=[resume_input, chatbot, thinking_panel, user_id, username, passenger_id],
            outputs=[chatbot, thinking_panel, status_bar],
        )
        approve_btn.click(
            lambda t, h, th, uid, un, pid: _resume_interrupt(t, h, th, uid, un, pid, approve=True),
            inputs=[resume_input, chatbot, thinking_panel, user_id, username, passenger_id],
            outputs=[chatbot, thinking_panel, status_bar],
        )
        reject_btn.click(
            lambda t, h, th, uid, un, pid: _resume_interrupt(t, h, th, uid, un, pid, approve=False),
            inputs=[resume_input, chatbot, thinking_panel, user_id, username, passenger_id],
            outputs=[chatbot, thinking_panel, status_bar],
        )

        demo.load(_check_agent_status, outputs=[agent_status])

    return demo


def main():
    app = create_app()
    # First element must be a Font object so Gradio's built-in-theme equality
    # check (Font.__eq__) doesn't crash comparing Font vs str. Font() declares
    # the name for CSS font-family without loading anything — correct for a
    # system font. Calibri is a Windows font; the fallbacks cover macOS/Linux.
    simple_font = (gr.themes.Font("Calibri"), "Arial", "Helvetica", "sans-serif")
    simple_mono = (gr.themes.Font("Consolas"), "Menlo", "Courier New", "monospace")
    app.launch(
        server_name=GRADIO_HOST,
        server_port=GRADIO_PORT,
        share=False,
        theme=gr.themes.Soft(font=simple_font, font_mono=simple_mono),
    )


if __name__ == "__main__":
    main()
