#!/usr/bin/env python3
"""
CLI integration test for the AI Travel Assistant agent.

Runs the agent backend ONLY (no FastAPI, no Gradio) and streams the full
execution to the terminal so you can validate the end-to-end workflow:

  - System messages injected by middleware (e.g. ContextInjectionMiddleware)
  - Human messages
  - AI messages and token-by-token visible text
  - Model thinking / reasoning (chain-of-thought)
  - Tool calls (start + args + result) for every tool, including the `task`
    tool that delegates to sub-agents, and `write_todos` that builds the plan
  - The DeepAgent to-do list (plan) with per-item status
  - Human-in-the-loop interrupts (request_travel_info + book/cancel approvals),
    which you can resume from the terminal

Prerequisites (must already be running):
  - Redis on localhost:6379          (short-term memory)
  - MongoDB on localhost:27017       (long-term memory)
  - MCP tool server on 127.0.0.1:8000 (business tools)
  - SANDBOX_DOMAIN set in .env       (OpenSandbox)

You can start Redis, MongoDB and the MCP server together with:
    uv run python demo/run_demo.py --skip-ui

Then run this test in another terminal:
    uv run python test/agent_cli_test.py --message "Search flights from SFO to JFK"
    uv run python test/agent_cli_test.py -m "I want to rent a car in Singapore" \\
        --user-id u_001 --username Alice

Interactive: when an interrupt fires, type your answer (or `approve`/`reject`
for approval interrupts) and press Enter to resume the agent.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.types import Command

from agent.logger import logger
from agent.main_agent import create_main_agent
from agent.schema import TravelContext

# --------------------------------------------------------------------------- #
# Terminal colors (optional, degrades gracefully on non-ANSI terminals)
# --------------------------------------------------------------------------- #
_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def _dim(text: str) -> str:
    return _c("2;37", text)


def _cyan(text: str) -> str:
    return _c("36", text)


def _yellow(text: str) -> str:
    return _c("33", text)


def _green(text: str) -> str:
    return _c("32", text)


def _red(text: str) -> str:
    return _c("31", text)


def _magenta(text: str) -> str:
    return _c("35", text)


def _bold(text: str) -> str:
    return _c("1", text)


# --------------------------------------------------------------------------- #
# Source / reasoning extraction (mirrors api_view/services/stream_mapper.py)
# --------------------------------------------------------------------------- #
def _source_from_metadata(metadata: dict[str, Any] | None) -> str:
    if not metadata:
        return "main"
    node = metadata.get("langgraph_node", "")
    if node.endswith("-agent") or node.endswith("_subagent"):
        return node
    checkpoint_ns = metadata.get("checkpoint_ns", "")
    if checkpoint_ns:
        return checkpoint_ns
    return "main"


def _extract_reasoning(msg: Any) -> str:
    """Pull model chain-of-thought out of DeepSeek / OpenAI-compatible chunks."""
    additional = getattr(msg, "additional_kwargs", None) or {}
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = additional.get(key)
        if isinstance(value, str) and value:
            return value
    response_metadata = getattr(msg, "response_metadata", None) or {}
    for key in ("reasoning_content", "reasoning"):
        value = response_metadata.get(key)
        if isinstance(value, str) and value:
            return value
    content = msg.content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype in ("thinking", "reasoning"):
                text = block.get("thinking") or block.get("text") or block.get("content", "")
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return ""


def _extract_visible_text(msg: Any) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in ("text", "output_text", ""):
                parts.append(str(block.get("text") or block.get("content", "")))
        return "".join(parts)
    return str(content) if content else ""


def _format_args(args: Any) -> str:
    if isinstance(args, str):
        return args
    try:
        return json.dumps(args, ensure_ascii=False)
    except Exception:
        return str(args)


def _short(text: str, limit: int = 4000) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f" …<+{len(text) - limit} chars>"


# --------------------------------------------------------------------------- #
# Stream printing
# --------------------------------------------------------------------------- #
def _print_plan(source: str, todos: list[dict]) -> None:
    label = _bold(_yellow(f"[PLAN|{source}]"))
    print(f"\n{label} To-do list updated:")
    status_icon = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]"}
    for t in todos:
        status = t.get("status", "?")
        icon = status_icon.get(status, f"[{status}]")
        content = t.get("content", "")
        mark = ""
        if status == "completed":
            mark = _green(icon)
        elif status == "in_progress":
            mark = _cyan(icon)
        else:
            mark = _dim(icon)
        print(f"    {mark} {content}")
    print()


def _print_message(msg: Any, source: str) -> None:
    # System messages (e.g. ContextInjectionMiddleware, SkillsSync notification)
    if isinstance(msg, SystemMessage):
        text = _extract_visible_text(msg)
        print(f"\n{_bold(_magenta(f'[SYSTEM|{source}]'))} {_short(text, 2000)}")
        return

    # Human messages
    if isinstance(msg, HumanMessage):
        text = _extract_visible_text(msg)
        print(f"\n{_bold(_green(f'[HUMAN|{source}]'))} {text}")
        return

    # Tool results
    if isinstance(msg, ToolMessage):
        result = msg.content if isinstance(msg.content, str) else _format_args(msg.content)
        print(f"\n{_bold(_cyan(f'[TOOL RESULT|{source}]'))} {msg.name or 'tool'}")
        print(_dim(_short(result, 4000)))
        return

    # AI messages / chunks (reasoning + text + tool calls)
    if isinstance(msg, (AIMessage, AIMessageChunk)):
        reasoning = _extract_reasoning(msg)
        if reasoning:
            print(f"\n{_bold(_dim(f'[THINKING|{source}]'))}")
            print(_dim(_short(reasoning, 4000)))

        text = _extract_visible_text(msg)
        if text:
            print(f"\n{_bold(f'[AI|{source}]')} {text}")

        # Tool calls embedded in the AI message
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {})
            if name == "task":
                desc = ""
                if isinstance(args, dict):
                    desc = args.get("description", args.get("subagent_type", ""))
                print(
                    f"\n{_bold(_yellow(f'[DELEGATE|{source}]'))} task -> "
                    f"{_short(desc or _format_args(args), 800)}"
                )
            elif name == "write_todos":
                print(f"\n{_bold(_yellow(f'[WRITE_TODOS|{source}]'))} {_short(_format_args(args), 800)}")
            else:
                print(
                    f"\n{_bold(_yellow(f'[TOOL START|{source}]'))} {name}"
                    f"({_short(_format_args(args), 800)})"
                )
        return

    # Fallback for any other message type
    label = type(msg).__name__
    print(f"\n{_bold(f'[{label}|{source}]')} {_short(_format_args(getattr(msg, 'content', '')), 1000)}")


# --------------------------------------------------------------------------- #
# Interrupt handling
# --------------------------------------------------------------------------- #
def _classify_interrupt(value: Any) -> tuple[str, dict]:
    """Return (interrupt_type, payload_dict) for an interrupt value."""
    payload = value.model_dump() if hasattr(value, "model_dump") else value
    if not isinstance(payload, dict):
        payload = {"raw": str(payload)}
    if payload.get("type") == "travel_info_request":
        return "travel_info_request", payload
    if "action_requests" in payload or hasattr(value, "action_requests"):
        return "approval", payload
    return "unknown", payload


async def _stream(agent: Any, input_data: Any, config: dict, context: TravelContext) -> None:
    """Stream one invocation (initial input or a resume Command) to the terminal."""
    async for chunk in agent.astream(
        input_data,
        config=config,
        context=context,
        stream_mode=["messages", "updates"],
        subgraphs=True,
    ):
        # Normalise the chunk into (mode, data, source)
        if isinstance(chunk, tuple) and len(chunk) == 3:
            namespace, mode, data = chunk
            source = ".".join(namespace) if namespace else "main"
        elif isinstance(chunk, tuple) and len(chunk) == 2:
            mode, data = chunk
            source = "main"
        else:
            continue

        if mode == "messages":
            msg_chunk, metadata = data
            source = _source_from_metadata(metadata) or source
            _print_message(msg_chunk, source)

        elif mode == "updates":
            if not isinstance(data, dict):
                continue
            for _node, update in data.items():
                if not isinstance(update, dict):
                    continue
                todos = update.get("todos")
                if todos is not None:
                    _print_plan(source, todos)
                # Some updates carry full messages too (e.g. sub-agent returns)
                for m in update.get("messages", []) or []:
                    _print_message(m, source)


async def _handle_interrupts(agent: Any, config: dict, context: TravelContext) -> bool:
    """Check for pending interrupts and resume interactively.

    Returns True if a resume was performed (caller should keep looping),
    False if there are no pending interrupts.
    """
    state = await agent.aget_state(config)
    if not state or not state.interrupts:
        return False

    for intr in state.interrupts:
        value = getattr(intr, "value", intr)
        intr_id = getattr(intr, "id", "unknown")
        itype, payload = _classify_interrupt(value)

        print("\n" + "=" * 78)
        print(_bold(_red(f"[INTERRUPT|{itype}] id={intr_id}")))
        if itype == "travel_info_request":
            print(f"  Missing fields : {payload.get('missing_fields', '')}")
            print(f"  Collected data : {payload.get('collected_data', '')}")
            print(_dim("  Type the missing info as free text (or `exit` to stop):"))
        elif itype == "approval":
            print(f"  Payload        : {_short(_format_args(payload), 1000)}")
            print(_dim("  Type `approve` or `reject` (or `exit` to stop):"))
        else:
            print(f"  Payload        : {_short(_format_args(payload), 1000)}")
            print(_dim("  Type a resume value (or `exit` to stop):"))
        print("=" * 78)

        raw = input(_bold("> ")).strip()
        if not raw or raw.lower() == "exit":
            print(_yellow("\nInterrupt not resumed — session paused. "
                          "Re-run with the same --thread-id to continue."))
            return False

        if itype == "approval":
            decision = "approve" if raw.lower().startswith("approve") else "reject"
            resume_value = {"decisions": [{"type": decision}]}
        else:
            # request_travel_info expects the raw human text; the sub-agent
            # parses it as free text.
            resume_value = raw

        print(_cyan(f"\n[RESUME] {_format_args(resume_value)[:300]}\n"))
        await _stream(agent, Command(resume=resume_value), config, context)
        # A resume may trigger further interrupts (e.g. search -> approval).
        return True

    return False


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
async def main() -> int:
    parser = argparse.ArgumentParser(description="CLI integration test for the travel agent.")
    parser.add_argument("-m", "--message", default=None,
                        help="First user message. If omitted, an interactive prompt is shown.")
    parser.add_argument("--user-id", default="u_cli_test",
                        help="user_id for TravelContext (drives /memories/{user_id}/).")
    parser.add_argument("--username", default="CLI-Tester",
                        help="username for TravelContext.")
    parser.add_argument("--passenger-id", default="p_001",
                        help="passenger_id passed to flight MCP tools via runtime config.")
    parser.add_argument("--thread-id", default=None,
                        help="Reuse an existing conversation thread. New UUID if omitted.")
    parser.add_argument("--sandbox-id", default=None,
                        help="Reuse an existing OpenSandbox id. New sandbox if omitted.")
    args = parser.parse_args()

    thread_id = args.thread_id or str(uuid.uuid4())
    config: dict = {
        "configurable": {
            "thread_id": thread_id,
            "passenger_id": args.passenger_id,
        }
    }
    context = TravelContext(user_id=args.user_id, username=args.username)

    print(_bold(_magenta("\n=== Building the agent (this connects to the sandbox) ===\n")))
    agent = await create_main_agent(sandbox_id=args.sandbox_id)
    print(_bold(_green("\n=== Agent ready ===\n")))
    print(_dim(f"thread_id   = {thread_id}"))
    print(_dim(f"user_id     = {context.user_id}"))
    print(_dim(f"username    = {context.username}"))
    print(_dim(f"passenger_id= {args.passenger_id}"))
    print(_dim("Tip: re-run with --thread-id <above> to continue this conversation.\n"))

    # Seed the first message (from CLI arg or interactive prompt).
    first_message = args.message
    if first_message is None:
        print(_bold("Enter your message (Ctrl+C to quit):"))
        first_message = input(_bold("> ")).strip()
    if not first_message:
        print(_yellow("No message provided, exiting."))
        return 0

    # ---- Turn loop: send message -> stream -> handle interrupts -> next turn ----
    current_input: Any = {"messages": [HumanMessage(content=first_message)]}
    while True:
        print("\n" + "=" * 78)
        print(_bold(_green(f"[TURN] sending message -> thread {thread_id}")))
        print("=" * 78)
        await _stream(agent, current_input, config, context)

        # Drain any interrupts that fire during this turn (may chain).
        while await _handle_interrupts(agent, config, context):
            pass

        # Next turn: read another message from the terminal.
        print("\n" + "-" * 78)
        print(_bold("Next message (Ctrl+C to quit, or empty to end):"))
        try:
            nxt = input(_bold("> ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not nxt:
            break
        current_input = {"messages": [HumanMessage(content=nxt)]}

    print(_bold(_magenta("\n=== CLI test finished ===\n")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print(_yellow("\nInterrupted by user."))
        sys.exit(130)
