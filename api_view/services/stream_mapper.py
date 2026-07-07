"""Map LangGraph stream chunks to SSE events."""

from __future__ import annotations

import json
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


def _sse(event: Any) -> str:
    return f"data: {event.model_dump_json()}\n\n"


def _source_from_metadata(metadata: dict[str, Any] | None) -> str:
    if not metadata:
        return "main"
    node = metadata.get("langgraph_node", "")
    if "subagent" in node or node.endswith("_subagent"):
        return node
    checkpoint_ns = metadata.get("checkpoint_ns", "")
    if checkpoint_ns:
        return checkpoint_ns
    return "main"


def _format_tool_args(args: Any) -> str:
    if isinstance(args, str):
        return args
    return json.dumps(args, ensure_ascii=False)


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
            elif isinstance(chunk, tuple) and len(chunk) == 2:
                mode, data = chunk
                source = "main"
            else:
                continue

            if mode == "messages":
                msg_chunk, metadata = data
                source = _source_from_metadata(metadata) or source

                if isinstance(msg_chunk, (AIMessageChunk, AIMessage)):
                    reasoning = _extract_reasoning(msg_chunk)
                    if reasoning:
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
                    if text:
                        full_response += text
                        yield _sse(StreamTokenEvent(content=text, source=source))

                    if hasattr(msg_chunk, "tool_call_chunks") and msg_chunk.tool_call_chunks:
                        for tc in msg_chunk.tool_call_chunks:
                            tc_id = tc.get("id") or tc.get("index", "")
                            name = tc.get("name", "")
                            if name:
                                pending_tool_calls[str(tc_id)] = {"name": name, "args": ""}
                                yield _sse(
                                    StreamToolStartEvent(
                                        tool_call_id=str(tc_id),
                                        tool_name=name,
                                        source=source,
                                    )
                                )
                                thinking = _thinking_for_tool(name, tc.get("args", {}), source)
                                yield _sse(thinking)
                            if tc.get("args"):
                                args_str = _format_tool_args(tc["args"])
                                key = str(tc_id)
                                if key in pending_tool_calls:
                                    pending_tool_calls[key]["args"] += args_str
                                yield _sse(StreamToolArgsEvent(args=args_str))

                    if isinstance(msg_chunk, AIMessage) and msg_chunk.tool_calls:
                        for tc in msg_chunk.tool_calls:
                            tc_id = tc.get("id", "")
                            name = tc.get("name", "")
                            args = tc.get("args", {})
                            yield _sse(
                                StreamToolStartEvent(
                                    tool_call_id=tc_id,
                                    tool_name=name,
                                    source=source,
                                )
                            )
                            yield _sse(_thinking_for_tool(name, args, source))
                            yield _sse(StreamToolArgsEvent(args=_format_tool_args(args)))

                elif isinstance(msg_chunk, ToolMessage):
                    result_text = (
                        msg_chunk.content
                        if isinstance(msg_chunk.content, str)
                        else json.dumps(msg_chunk.content, ensure_ascii=False)
                    )
                    yield _sse(
                        StreamToolResultEvent(
                            tool_name=msg_chunk.name or "tool",
                            result=result_text[:4000],
                            source=source,
                        )
                    )
                    yield _sse(
                        StreamThinkingEvent(
                            category="tool",
                            content=f"Tool completed: {msg_chunk.name or 'tool'}",
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
                        yield _sse(StreamPlanEvent(todos=todos, source=source))
                        summary = ", ".join(
                            f"[{t.get('status', '?')}] {t.get('content', '')}" for t in todos
                        )
                        yield _sse(
                            StreamThinkingEvent(
                                category="plan",
                                content=f"Plan updated: {summary}",
                                source=source,
                                metadata={"todos": todos},
                            )
                        )

        state = await agent.aget_state(config)
        if state and state.interrupts:
            for intr in state.interrupts:
                for event in _extract_interrupts({"__interrupt__": [intr]}, thread_id):
                    yield _sse(event)

        yield _sse(StreamDoneEvent(thread_id=thread_id, content=full_response))

    except Exception as exc:
        yield _sse(StreamErrorEvent(message=str(exc)))
