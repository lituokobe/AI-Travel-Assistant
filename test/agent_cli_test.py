#!/usr/bin/env python3
"""
CLI integration test for the AI Travel Assistant agent.

Runs the agent backend ONLY (no FastAPI, no Gradio) and prints an ORGANIZED
transcript of each turn so you can validate the end-to-end workflow:

  - TODO LIST      — the DeepAgent plan, with per-item status, printed whenever
                     it changes.
  - THINKING       — the model's chain-of-thought, printed as a single block
                     (not per token).
  - MESSAGE HISTORY— every message in order, cleanly labelled:
                       [SYSTEM | src]  middleware injections (context, skills…)
                       [HUMAN  | src]  user messages
                       [TOOL   | src]  tool call name(args)
                       [RESULT | src]  tool result
                       [AI     | src]  assistant reply text
                     Duplicated  per-token chunks and internal middleware LLM
                     noise are suppressed.

Human-in-the-loop interrupts (request_travel_info + book/cancel approvals) are
surfaced and can be resumed from the terminal.

Prerequisites (must already be running):
  - Redis on localhost:6379           (short-term memory)
  - MongoDB on localhost:27017        (long-term memory)
  - MCP tool server on 127.0.0.1:8000 (business tools)
  - SANDBOX_DOMAIN set in .env        (OpenSandbox)

Start them with:
    uv run python demo/run_demo.py --skip-ui

Then in another terminal:
    uv run python test/agent_cli_test.py -m "Search flights from SFO to JFK"
    uv run python test/agent_cli_test.py -m "I want to rent a car in Singapore" \
        --user-id u_001 --username Alice

Interactive: when an interrupt fires, type your answer (or `approve`/`reject`
for approval interrupts) and press Enter to resume the agent.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
import warnings
from pathlib import Path
from typing import Any

# Make the project root importable when running this file directly.
# pytest gets this via conftest.py, but a direct script invocation does not.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.types import Command

from agent.main_agent import create_main_agent
from agent.schema import TravelContext

# --------------------------------------------------------------------------- #
# Silence the very chatty third-party loggers + deprecation warnings.
# agent.logger configures the root logger at INFO with force=True, which would
# otherwise flood the console with every httpx HTTP request, every opensandbox
# adapter call and every LangChain deprecation warning. The test prints its own
# organized output, so we keep the console at WARNING+ only.
# --------------------------------------------------------------------------- #
logging.getLogger().setLevel(logging.WARNING)
for _noisy in (
    "httpx", "httpcore", "openai", "deepagents", "opensandbox",
    "langchain", "langgraph", "urllib3", "pymongo",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logging.getLogger("agent").setLevel(logging.WARNING)
warnings.filterwarnings("ignore")

# --------------------------------------------------------------------------- #
# Terminal colors (degrades gracefully on non-ANSI terminals)
# --------------------------------------------------------------------------- #
_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


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
# Source / reasoning extraction
# --------------------------------------------------------------------------- #
def _clean_source(namespace: tuple[str, ...] | list[str], metadata: dict | None) -> str:
    """Resolve a readable source name (main / car-agent / flights-agent / …).

    The streaming chunk's langgraph_node is often `model:<id>`, which is ugly
    and meaningless to a human. We prefer the subgraph namespace (which already
    identifies the sub-agent when subgraphs=True), and only let metadata refine
    it when it is a clean agent name.
    """
    ns_source = ".".join(namespace) if namespace else "main"
    if metadata:
        node = metadata.get("langgraph_node", "")
        if node.endswith("-agent") or node.endswith("_subagent"):
            return node
        cp = metadata.get("checkpoint_ns", "")
        if cp and cp.endswith("-agent"):
            return cp
    return ns_source


def _is_internal_source(src: str) -> bool:
    """Hide middleware-internal LLM calls (e.g. MemoryUpdateMiddleware)."""
    return "Middleware" in src or "after_agent" in src or "before_agent" in src


def _extract_reasoning(msg: Any) -> str:
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
            if isinstance(block, dict) and block.get("type") in ("thinking", "reasoning"):
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


def _short(text: str, limit: int = 1500) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f" …<+{len(text) - limit} chars>"


def _msg_key(msg: Any) -> str:
    """Stable dedup key for a message across stream modes."""
    mid = getattr(msg, "id", None)
    if mid:
        return str(mid)
    content = getattr(msg, "content", "")
    return f"{type(msg).__name__}:{hash(str(content))}"


# --------------------------------------------------------------------------- #
# Organized printer with per-source buffering (no per-token noise)
# --------------------------------------------------------------------------- #
class TranscriptPrinter:
    """Buffers reasoning/text per source and prints clean, deduped blocks."""

    def __init__(self) -> None:
        self._think: dict[str, list[str]] = {}
        self._text: dict[str, list[str]] = {}
        self._seen_msgs: set[str] = set()
        self._seen_tool_ids: set[str] = set()
        self._last_todos_key: str = ""

    # -- buffering --
    def _buffer_reasoning(self, src: str, text: str) -> None:
        if text:
            self._think.setdefault(src, []).append(text)

    def _buffer_text(self, src: str, text: str) -> None:
        if text:
            self._text.setdefault(src, []).append(text)

    def _flush(self, src: str) -> None:
        think = self._think.pop(src, [])
        if think:
            joined = "".join(think).strip()
            if joined:
                print(f"\n{_bold(_dim(f'[THINKING | {src}]'))}")
                print(_dim(_short(joined, 2000)))
        text = self._text.pop(src, [])
        if text:
            joined = "".join(text).strip()
            if joined:
                print(f"\n{_bold(f'[AI | {src}]')} {joined}")

    def flush_all(self) -> None:
        for src in list(self._think.keys()) + list(self._text.keys()):
            self._flush(src)

    # -- printing --
    def plan(self, src: str, todos: list[dict]) -> None:
        key = json.dumps(todos, ensure_ascii=False, sort_keys=True)
        if key == self._last_todos_key or not todos:
            return
        self._last_todos_key = key
        icons = {"completed": _green("[x]"), "in_progress": _cyan("[>]"), "pending": _dim("[ ]")}
        print(f"\n{_bold(_yellow(f'[TODO LIST | {src}]'))}")
        for t in todos:
            status = t.get("status", "?")
            icon = icons.get(status, f"[{status}]")
            print(f"    {icon} {t.get('content', '')}")

    def tool_call(self, src: str, name: str, args: Any, tc_id: str) -> None:
        if tc_id and tc_id in self._seen_tool_ids:
            return
        if tc_id:
            self._seen_tool_ids.add(tc_id)
        self._flush(src)
        if name == "task":
            desc = ""
            if isinstance(args, dict):
                desc = args.get("description") or args.get("subagent_type") or ""
            print(f"\n{_bold(_yellow(f'[DELEGATE | {src}]'))} task → {_short(desc or _format_args(args), 600)}")
        elif name == "write_todos":
            print(f"\n{_bold(_yellow(f'[PLAN UPDATE | {src}]'))} write_todos({_short(_format_args(args), 400)})")
        else:
            print(f"\n{_bold(_yellow(f'[TOOL | {src}]'))} {name}({_short(_format_args(args), 600)})")

    def tool_result(self, src: str, name: str, content: Any, tc_id: str = "") -> None:
        if tc_id and tc_id in self._seen_tool_ids:
            # a tool call and its result share the same tool_call_id; the call
            # was already recorded, so we don't re-add the id — just print.
            pass
        text = content if isinstance(content, str) else _format_args(content)
        self._flush(src)
        print(f"\n{_bold(_cyan(f'[RESULT | {src}]'))} {name or 'tool'}")
        print(_dim(_short(text, 1500)))

    def system(self, src: str, text: str) -> None:
        self._flush(src)
        print(f"\n{_bold(_magenta(f'[SYSTEM | {src}]'))} {_short(text, 1000)}")

    def human(self, src: str, text: str) -> None:
        self._flush(src)
        print(f"\n{_bold(_green(f'[HUMAN | {src}]'))} {text}")

    def ai_message(self, src: str, msg: AIMessage) -> None:
        """Print a consolidated AI message: flush its reasoning, then text + tool calls."""
        reasoning = _extract_reasoning(msg)
        if reasoning:
            self._buffer_reasoning(src, reasoning)
        # flush reasoning (and any buffered chunk text) before the message body
        self._flush(src)
        text = _extract_visible_text(msg)
        if text:
            print(f"\n{_bold(f'[AI | {src}]')} {text}")
        for tc in msg.tool_calls or []:
            self.tool_call(src, tc.get("name", ""), tc.get("args", {}), tc.get("id", ""))

    def handle_message(self, msg: Any, src: str) -> None:
        """Route a full (non-chunk) message to the right printer, with dedup."""
        if _is_internal_source(src):
            return
        key = _msg_key(msg)
        if key in self._seen_msgs:
            return
        self._seen_msgs.add(key)

        if isinstance(msg, SystemMessage):
            self.system(src, _extract_visible_text(msg))
        elif isinstance(msg, HumanMessage):
            self.human(src, _extract_visible_text(msg))
        elif isinstance(msg, ToolMessage):
            self.tool_result(src, msg.name or "tool", msg.content,
                             getattr(msg, "tool_call_id", ""))
        elif isinstance(msg, AIMessage):
            self.ai_message(src, msg)
        # AIMessageChunk is handled separately (reasoning buffering only).


# --------------------------------------------------------------------------- #
# Streaming one invocation
# --------------------------------------------------------------------------- #
async def _stream(agent: Any, input_data: Any, config: dict,
                  context: TravelContext, printer: TranscriptPrinter) -> None:
    async for chunk in agent.astream(
        input_data,
        config=config,
        context=context,
        stream_mode=["messages", "updates"],
        subgraphs=True,
    ):
        if isinstance(chunk, tuple) and len(chunk) == 3:
            namespace, mode, data = chunk
        elif isinstance(chunk, tuple) and len(chunk) == 2:
            mode, data = chunk
            namespace = ()
        else:
            continue

        if mode == "messages":
            msg_chunk, metadata = data
            src = _clean_source(namespace, metadata)
            if _is_internal_source(src):
                continue
            # Chunks are used ONLY to capture reasoning silently; their per-token
            # text and partial tool_call_chunks are ignored to avoid noise/dups.
            if isinstance(msg_chunk, AIMessageChunk):
                reasoning = _extract_reasoning(msg_chunk)
                if reasoning:
                    printer._buffer_reasoning(src, reasoning)
                continue
            # Full (non-chunk) messages are printed cleanly + deduped.
            printer.handle_message(msg_chunk, src)

        elif mode == "updates":
            if not isinstance(data, dict):
                continue
            for _node, update in data.items():
                if not isinstance(update, dict):
                    continue
                todos = update.get("todos")
                if todos is not None:
                    src = _clean_source(namespace, None)
                    printer.plan(src, todos)
                for m in update.get("messages", []) or []:
                    src = _clean_source(namespace, None)
                    printer.handle_message(m, src)

    printer.flush_all()


# --------------------------------------------------------------------------- #
# Interrupt handling
# --------------------------------------------------------------------------- #
def _classify_interrupt(value: Any) -> tuple[str, dict]:
    payload = value.model_dump() if hasattr(value, "model_dump") else value
    if not isinstance(payload, dict):
        payload = {"raw": str(payload)}
    if payload.get("type") == "travel_info_request":
        return "travel_info_request", payload
    if "action_requests" in payload or hasattr(value, "action_requests"):
        return "approval", payload
    return "unknown", payload


async def _handle_interrupts(agent: Any, config: dict, context: TravelContext,
                             printer: TranscriptPrinter) -> bool:
    state = await agent.aget_state(config)
    if not state or not state.interrupts:
        return False

    for intr in state.interrupts:
        value = getattr(intr, "value", intr)
        intr_id = getattr(intr, "id", "unknown")
        itype, payload = _classify_interrupt(value)

        print("\n" + "=" * 78)
        print(_bold(_red(f"[INTERRUPT | {itype}] id={intr_id}")))
        if itype == "travel_info_request":
            print(f"  Missing fields : {payload.get('missing_fields', '')}")
            print(f"  Collected data : {payload.get('collected_data', '')}")
            print(_dim("  Type the missing info as free text (or `exit` to stop):"))
        elif itype == "approval":
            print(f"  Payload        : {_short(_format_args(payload), 800)}")
            print(_dim("  Type `approve` or `reject` (or `exit` to stop):"))
        else:
            print(f"  Payload        : {_short(_format_args(payload), 800)}")
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
            resume_value = raw

        print(_cyan(f"\n[RESUME] {_short(_format_args(resume_value), 300)}\n"))
        await _stream(agent, Command(resume=resume_value), config, context, printer)
        return True  # a resume may trigger further interrupts

    return False


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
async def main() -> int:
    parser = argparse.ArgumentParser(description="CLI integration test for the travel agent.")
    parser.add_argument("-m", "--message", default=None,
                        help="First user message. If omitted, an interactive prompt is shown.")
    parser.add_argument("--user-id", default="3442 587242",
                        help="user_id for TravelContext (also used as flight passenger_id).")
    parser.add_argument("--username", default="Luis",
                        help="username for TravelContext.")
    parser.add_argument("--passenger-id", default=None,
                        help="Optional override; defaults to --user-id (flights DB alias).")
    parser.add_argument("--thread-id", default=None,
                        help="Reuse an existing conversation thread. New UUID if omitted.")
    parser.add_argument("--sandbox-id", default=None,
                        help="Reuse an existing OpenSandbox id. New sandbox if omitted.")
    args = parser.parse_args()

    passenger_id = args.passenger_id or args.user_id
    thread_id = args.thread_id or str(uuid.uuid4())
    config: dict = {
        "configurable": {
            "thread_id": thread_id,
            "passenger_id": passenger_id,
        }
    }
    context = TravelContext(user_id=args.user_id, username=args.username)

    print(_bold(_magenta("\n=== Building the agent (this connects to the sandbox) ===\n")))
    agent = await create_main_agent(sandbox_id=args.sandbox_id)
    print(_bold(_green("\n=== Agent ready ===\n")))
    print(_dim(f"thread_id    = {thread_id}"))
    print(_dim(f"user_id      = {context.user_id}"))
    print(_dim(f"username     = {context.username}"))
    print(_dim(f"passenger_id = {passenger_id} (= user_id for flights)"))
    print(_dim("Tip: re-run with --thread-id <above> to continue this conversation.\n"))

    first_message = args.message
    if first_message is None:
        print(_bold("Enter your message (Ctrl+C to quit):"))
        first_message = input(_bold("> ")).strip()
    if not first_message:
        print(_yellow("No message provided, exiting."))
        return 0

    printer = TranscriptPrinter()
    current_input: Any = {"messages": [HumanMessage(content=first_message)]}
    turn = 0
    while True:
        turn += 1
        print("\n" + "=" * 78)
        print(_bold(_green(f"[TURN {turn}] → thread {thread_id}")))
        print("=" * 78)
        # Show the user's own message as a clean HUMAN line at the top of the turn.
        printer.human("main", first_message if turn == 1 else current_input["messages"][0].content)

        await _stream(agent, current_input, config, context, printer)

        # Drain any interrupts that fire during this turn (may chain).
        while await _handle_interrupts(agent, config, context, printer):
            pass

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
