"""Map LangGraph stream chunks to SSE events."""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from agent.schema import (
    StreamDoneEvent,
    StreamErrorEvent,
    StreamTokenEvent,
    StreamToolArgsEvent,
    StreamToolResultEvent,
    StreamToolStartEvent,
)
from api_view.models.events import (
    StreamInterruptEvent,
    StreamPlanEvent,
    StreamReasoningEvent,
    StreamThinkingEvent,
)
from agent.logger import logger
from agent.middlewares.memory_update import MEMORY_UPDATE_TAG

# Trailing JSON that MemoryUpdateMiddleware asks the LLM to emit
# (leaks into astream when the internal call is not filtered).
_MEMORY_JSON_TAIL = re.compile(
    r'\s*\{\s*"destinations"\s*:\s*\[.*?\]\s*,\s*"query"\s*:\s*".*?"\s*\}\s*$',
    re.DOTALL,
)


def _sse(event: Any) -> str:
    # Yield the raw JSON payload only. EventSourceResponse adds the
    # `data: ` prefix + blank-line separator itself; pre-formatting it here
    # would double-encode to `data: data: {...}` and break clients.
    return event.model_dump_json()


def _source_from_metadata(metadata: dict[str, Any] | None) -> str:
    if not metadata:
        return "main"
    node = metadata.get("langgraph_node", "")
    # Sub-agent node names use the hyphen "-agent" suffix (e.g. "car-agent").
    # The legacy "_subagent" check is kept as a fallback for any in-flight
    # sessions created before the rename.
    if node.endswith("-agent") or node.endswith("_subagent"):
        return node
    checkpoint_ns = metadata.get("checkpoint_ns", "")
    if checkpoint_ns:
        return checkpoint_ns
    return "main"


def _format_tool_args(args: Any) -> str:
    if isinstance(args, str):
        return args
    return json.dumps(args, ensure_ascii=False)


def _normalize_tool_call(tc: Any) -> tuple[str, str, Any]:
    """Return (tool_call_id, tool_name, args) with a guaranteed non-empty string id.

    Streaming chunks often set ``id=None`` while the key is still present, so
    ``dict.get("id", "")`` incorrectly returns ``None`` and breaks Pydantic.
    """
    if isinstance(tc, dict):
        tc_id = tc.get("id")
        name = tc.get("name") or ""
        args = tc.get("args", {})
        index = tc.get("index")
    else:
        tc_id = getattr(tc, "id", None)
        name = getattr(tc, "name", None) or ""
        args = getattr(tc, "args", None) or {}
        index = getattr(tc, "index", None)

    if not tc_id and index is not None:
        tc_id = f"idx-{index}"
    if not tc_id:
        tc_id = f"anon-{name or 'tool'}"
    return str(tc_id), str(name), args


def _is_internal_llm_run(metadata: dict[str, Any] | None) -> bool:
    """True for middleware/internal LLM calls that must not appear in the UI."""
    if not metadata:
        return False
    tags = metadata.get("tags") or []
    if MEMORY_UPDATE_TAG in tags:
        return True
    run_name = (
        metadata.get("langsmith_run_name")
        or metadata.get("run_name")
        or ""
    )
    if isinstance(run_name, str) and "memory_entity_extract" in run_name:
        return True
    return False


def _strip_trailing_memory_json(text: str) -> str:
    """Remove a trailing destinations/query JSON object if it leaked into chat text."""
    return _MEMORY_JSON_TAIL.sub("", text).rstrip()


def _extract_reasoning(msg_chunk: AIMessage | AIMessageChunk) -> str:
    """Extract model chain-of-thought from DeepSeek / OpenAI-compatible chunks."""
    additional = getattr(msg_chunk, "additional_kwargs", None) or {}
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = additional.get(key)
        if isinstance(value, str) and value:
            return value

    response_metadata = getattr(msg_chunk, "response_metadata", None) or {}
    for key in ("reasoning_content", "reasoning"):
        value = response_metadata.get(key)
        if isinstance(value, str) and value:
            return value

    content = msg_chunk.content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type in ("thinking", "reasoning"):
                text = block.get("thinking") or block.get("text") or block.get("content", "")
                if text:
                    parts.append(str(text))
        return "".join(parts)

    return ""


def _extract_visible_text(msg_chunk: AIMessage | AIMessageChunk) -> str:
    """Extract user-visible text, skipping reasoning blocks."""
    content = msg_chunk.content
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


def _thinking_for_tool(tool_name: str, args: Any, source: str) -> StreamThinkingEvent:
    if tool_name == "task":
        desc = ""
        if isinstance(args, dict):
            desc = args.get("description", args.get("subagent_type", ""))
        return StreamThinkingEvent(
            category="delegation",
            content=f"Delegating to sub-agent: {desc or json.dumps(args, ensure_ascii=False)}",
            source=source,
            metadata={"tool": tool_name, "args": args},
        )
    if tool_name == "write_todos":
        return StreamThinkingEvent(
            category="plan",
            content="Updating task plan (write_todos)",
            source=source,
            metadata={"tool": tool_name, "args": args},
        )
    return StreamThinkingEvent(
        category="tool",
        content=f"Calling tool: {tool_name}",
        source=source,
        metadata={"tool": tool_name, "args": args},
    )


def _extract_interrupts(result: dict[str, Any], thread_id: str) -> list[StreamInterruptEvent]:
    events: list[StreamInterruptEvent] = []
    interrupts = result.get("__interrupt__", [])
    for item in interrupts:
        value = getattr(item, "value", item)
        interrupt_id = getattr(item, "id", "unknown")
        if isinstance(value, dict) and value.get("type") == "travel_info_request":
            events.append(
                StreamInterruptEvent(
                    interrupt_id=interrupt_id,
                    interrupt_type="travel_info_request",
                    payload=value,
                    thread_id=thread_id,
                )
            )
        elif hasattr(value, "action_requests") or (
            isinstance(value, dict) and "action_requests" in value
        ):
            payload = value.model_dump() if hasattr(value, "model_dump") else value
            events.append(
                StreamInterruptEvent(
                    interrupt_id=interrupt_id,
                    interrupt_type="approval",
                    payload=payload if isinstance(payload, dict) else {"raw": str(payload)},
                    thread_id=thread_id,
                )
            )
        else:
            events.append(
                StreamInterruptEvent(
                    interrupt_id=interrupt_id,
                    interrupt_type="unknown",
                    payload={"value": str(value)},
                    thread_id=thread_id,
                )
            )
    return events


async def map_agent_stream(
    agent: Any,
    input_data: Any,
    config: dict[str, Any],
    context: Any,
    thread_id: str,
) -> AsyncIterator[str]:
    """Stream agent execution as SSE events."""
    full_response = ""
    pending_tool_calls: dict[str, dict[str, Any]] = {}
    # Buffer model chain-of-thought chunks and flush them as a single log
    # line so the reasoning reads as one block instead of hundreds of
    # tiny token-sized log entries.
    reasoning_buf: list[str] = []

    def _flush_reasoning(src: str) -> None:
        if reasoning_buf:
            logger.info("[reasoning|%s] %s", src, "".join(reasoning_buf))
            reasoning_buf.clear()

    def _emit_buffered_tool_args(tc_id: str, source: str) -> list[str]:
        """Emit one consolidated tool_args SSE for a buffered call (if any)."""
        info = pending_tool_calls.get(tc_id)
        if not info or info.get("args_emitted"):
            return []
        args_str = (info.get("args") or "").strip()
        if not args_str:
            return []
        info["args_emitted"] = True
        logger.info("[tool_args|%s] %s", source, args_str[:800])
        return [_sse(StreamToolArgsEvent(args=args_str))]

    try:
        async for chunk in agent.astream(
            input_data,
            config=config,
            context=context,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            if isinstance(chunk, tuple) and len(chunk) == 3:
                namespace, mode, data = chunk
                source = ".".join(namespace) if namespace else "main"
                is_root_graph = not namespace
            elif isinstance(chunk, tuple) and len(chunk) == 2:
                mode, data = chunk
                source = "main"
                is_root_graph = True
            else:
                continue

            if mode == "messages":
                msg_chunk, metadata = data
                if _is_internal_llm_run(metadata if isinstance(metadata, dict) else None):
                    continue
                source = _source_from_metadata(metadata) or source

                if isinstance(msg_chunk, (AIMessageChunk, AIMessage)):
                    reasoning = _extract_reasoning(msg_chunk)
                    if reasoning:
                        reasoning_buf.append(reasoning)
                        yield _sse(StreamReasoningEvent(content=reasoning, source=source))
                        yield _sse(
                            StreamThinkingEvent(
                                category="reasoning",
                                content=reasoning,
                                source=source,
                                metadata={"kind": "model_reasoning"},
                            )
                        )

                    text = _extract_visible_text(msg_chunk)
                    # Only root-graph assistant text goes to the chat bubble.
                    # Subgraph (sub-agent) narration stays out of the user reply;
                    # tool_result / thinking events still cover the under-the-hood story.
                    if text and is_root_graph:
                        full_response += text
                        yield _sse(StreamTokenEvent(content=text, source=source))

                    if hasattr(msg_chunk, "tool_call_chunks") and msg_chunk.tool_call_chunks:
                        for tc in msg_chunk.tool_call_chunks:
                            tc_id, name, chunk_args = _normalize_tool_call(tc)
                            if name and tc_id not in pending_tool_calls:
                                _flush_reasoning(source)
                                pending_tool_calls[tc_id] = {
                                    "name": name,
                                    "args": "",
                                    "args_emitted": False,
                                }
                                logger.info("[tool_start|%s] %s", source, name)
                                yield _sse(
                                    StreamToolStartEvent(
                                        tool_call_id=tc_id,
                                        tool_name=name,
                                        source=source,
                                    )
                                )
                                yield _sse(
                                    StreamThinkingEvent(
                                        category="tool",
                                        content=f"Calling tool: {name}",
                                        source=source,
                                        metadata={"tool": name},
                                    )
                                )
                            # Buffer arg fragments; emit once when the call completes.
                            if chunk_args and tc_id in pending_tool_calls:
                                pending_tool_calls[tc_id]["args"] += _format_tool_args(
                                    chunk_args
                                )

                    if isinstance(msg_chunk, AIMessage) and msg_chunk.tool_calls:
                        for tc in msg_chunk.tool_calls:
                            tc_id, name, args = _normalize_tool_call(tc)
                            if not name:
                                continue
                            args_str = _format_tool_args(args)
                            if tc_id not in pending_tool_calls:
                                _flush_reasoning(source)
                                pending_tool_calls[tc_id] = {
                                    "name": name,
                                    "args": args_str,
                                    "args_emitted": False,
                                }
                                logger.info("[tool_start|%s] %s", source, name)
                                yield _sse(
                                    StreamToolStartEvent(
                                        tool_call_id=tc_id,
                                        tool_name=name,
                                        source=source,
                                    )
                                )
                                yield _sse(_thinking_for_tool(name, args, source))
                            elif args_str:
                                pending_tool_calls[tc_id]["args"] = args_str
                            for event in _emit_buffered_tool_args(tc_id, source):
                                yield event

                elif isinstance(msg_chunk, ToolMessage):
                    _flush_reasoning(source)
                    tc_id = getattr(msg_chunk, "tool_call_id", None) or ""
                    if tc_id:
                        for event in _emit_buffered_tool_args(str(tc_id), source):
                            yield event
                    else:
                        # Fallback: flush oldest un-emitted buffered args
                        for pending_id, info in pending_tool_calls.items():
                            if not info.get("args_emitted") and info.get("args"):
                                for event in _emit_buffered_tool_args(pending_id, source):
                                    yield event
                                break

                    result_text = (
                        msg_chunk.content
                        if isinstance(msg_chunk.content, str)
                        else json.dumps(msg_chunk.content, ensure_ascii=False)
                    )
                    tool_name = msg_chunk.name or "tool"
                    logger.info(
                        "[tool_result|%s] %s: %s",
                        source,
                        tool_name,
                        result_text[:500],
                    )
                    yield _sse(
                        StreamToolResultEvent(
                            tool_name=tool_name,
                            result=result_text[:4000],
                            source=source,
                        )
                    )
                    yield _sse(
                        StreamThinkingEvent(
                            category="tool",
                            content=f"Tool completed: {tool_name}",
                            source=source,
                            metadata={"result_preview": result_text[:500]},
                        )
                    )

            elif mode == "updates":
                if not isinstance(data, dict):
                    continue
                for _node, update in data.items():
                    if not isinstance(update, dict):
                        continue
                    todos = update.get("todos")
                    if todos is not None:
                        _flush_reasoning(source)
                        summary = ", ".join(
                            f"[{t.get('status', '?')}] {t.get('content', '')}" for t in todos
                        )
                        logger.info("[plan|%s] %s", source, summary)
                        yield _sse(StreamPlanEvent(todos=todos, source=source))
                        yield _sse(
                            StreamThinkingEvent(
                                category="plan",
                                content=f"Plan updated: {summary}",
                                source=source,
                                metadata={"todos": todos},
                            )
                        )

        # Flush any tool args that never got a ToolMessage (edge cases)
        for pending_id in list(pending_tool_calls):
            for event in _emit_buffered_tool_args(pending_id, "main"):
                yield event

        state = await agent.aget_state(config)
        if state and state.interrupts:
            for intr in state.interrupts:
                for event in _extract_interrupts({"__interrupt__": [intr]}, thread_id):
                    _flush_reasoning("main")
                    if isinstance(event, StreamInterruptEvent):
                        logger.info(
                            "[interrupt|%s] id=%s payload=%s",
                            event.interrupt_type,
                            event.interrupt_id,
                            json.dumps(event.payload, ensure_ascii=False),
                        )
                    yield _sse(event)

        _flush_reasoning("main")
        full_response = _strip_trailing_memory_json(full_response)
        logger.info("[done|%s] %s", thread_id, full_response)
        yield _sse(StreamDoneEvent(thread_id=thread_id, content=full_response))

    except Exception as exc:
        _flush_reasoning("main")
        logger.error("[error] %s", exc, exc_info=True)
        yield _sse(StreamErrorEvent(message=str(exc)))
