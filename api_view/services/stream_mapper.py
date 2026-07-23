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


# Domain MCP tools are owned by child agents; LangGraph subgraph namespaces are
# often opaque (e.g. ``tools:<uuid>``), so we also infer the agent from the tool.
_TOOL_PREFIX_TO_AGENT: tuple[tuple[str, str], ...] = (
    ("hotels_", "hotels-agent"),
    ("flights_", "flights-agent"),
    ("car_", "car-agent"),
    ("activity_", "activity-agent"),
)

_SUBAGENT_TYPE_RE = re.compile(r'"subagent_type"\s*:\s*"([^"]+)"')
_KNOWN_SUBAGENTS = frozenset(
    {"hotels-agent", "flights-agent", "car-agent", "activity-agent"}
)

# Agent skills live under /skills/{scope}/{skill_name}/SKILL.md
_SKILL_MD_RE = re.compile(
    r"(?P<path>/skills/(?P<scope>[^/\s\"']+)/(?P<skill>[^/\s\"']+)/SKILL\.md)",
    re.IGNORECASE,
)
_FILE_PATH_ARG_KEYS = ("file_path", "path", "file", "filename")


def _agent_from_tool_name(tool_name: str | None) -> str | None:
    """Map a domain tool (e.g. hotels_search) to its owning child agent."""
    if not tool_name:
        return None
    for prefix, agent in _TOOL_PREFIX_TO_AGENT:
        if tool_name.startswith(prefix):
            return agent
    return None


def _agent_from_skills_path(text: str | None) -> str | None:
    """Infer child agent from filesystem skill paths like ``/skills/hotels/``."""
    if not text:
        return None
    for name in ("hotels", "flights", "car", "activity"):
        if f"/skills/{name}/" in text or f"/skills/{name}'" in text:
            return f"{name}-agent"
    return None


def _parse_subagent_type(args: Any) -> str | None:
    """Extract ``subagent_type`` from task-tool args (dict or partial JSON)."""
    if isinstance(args, dict):
        value = str(args.get("subagent_type") or "").strip()
        return value or None
    if not args:
        return None
    text = args if isinstance(args, str) else _format_tool_args(args)
    match = _SUBAGENT_TYPE_RE.search(text)
    if match:
        return match.group(1).strip() or None
    # Fallback: known agent id appears as a bare token in the args blob
    for agent in _KNOWN_SUBAGENTS:
        if agent in text:
            return agent
    return None


def _extract_path_from_tool_args(args: Any) -> str:
    """Best-effort file path from read_file-style tool args."""
    if isinstance(args, dict):
        for key in _FILE_PATH_ARG_KEYS:
            value = args.get(key)
            if value:
                return str(value)
        return ""
    if not args:
        return ""
    text = args if isinstance(args, str) else _format_tool_args(args)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            for key in _FILE_PATH_ARG_KEYS:
                value = parsed.get(key)
                if value:
                    return str(value)
    except (json.JSONDecodeError, TypeError):
        pass
    return text


def _parse_skill_activation(tool_name: str | None, args: Any) -> dict[str, str] | None:
    """
    Detect when a tool call activates or assigns an agent skill.

    DeepAgents skills are progressive docs: the model ``read_file``s
    ``/skills/{scope}/{skill}/SKILL.md``. ``assign_skill`` is our custom tool.
    Future skills under any scope are covered by the path pattern.
    """
    # Already-normalized skill info (e.g. carried on pending_tool_calls)
    if isinstance(args, dict) and args.get("skill") and args.get("action"):
        return {
            "skill": str(args["skill"]),
            "scope": str(args.get("scope") or "main"),
            "path": str(args.get("path") or ""),
            "action": str(args["action"]),
            **(
                {"agent": str(args["agent"])}
                if args.get("agent")
                else {}
            ),
        }

    name = (tool_name or "").strip()
    if name == "assign_skill":
        skill = ""
        agent = ""
        if isinstance(args, dict):
            skill = str(args.get("skill_name") or args.get("skill") or "").strip()
            agent = str(args.get("agent_name") or args.get("agent") or "").strip()
        else:
            text = args if isinstance(args, str) else _format_tool_args(args)
            m_skill = re.search(r'"skill_name"\s*:\s*"([^"]+)"', text or "")
            m_agent = re.search(r'"agent_name"\s*:\s*"([^"]+)"', text or "")
            skill = m_skill.group(1).strip() if m_skill else ""
            agent = m_agent.group(1).strip() if m_agent else ""
        if not skill:
            return None
        return {
            "skill": skill,
            "scope": agent or "main",
            "path": f"/skills/main/{skill}/SKILL.md",
            "action": "assign",
            "agent": agent or "main",
        }

    if name in ("read_file", "read_file_tool"):
        path = _extract_path_from_tool_args(args)
        match = _SKILL_MD_RE.search(path)
        if not match:
            # Also accept path-only fragments in streaming JSON
            match = _SKILL_MD_RE.search(str(args or ""))
        if not match:
            return None
        return {
            "skill": match.group("skill"),
            "scope": match.group("scope"),
            "path": match.group("path"),
            "action": "activate",
        }

    return None


def _skill_thinking_event(info: dict[str, str], source: str) -> StreamThinkingEvent:
    skill = info.get("skill") or "skill"
    action = info.get("action") or "activate"
    if action == "assign":
        agent = info.get("agent") or info.get("scope") or "main"
        content = f"Assign skill: {skill} → {agent}"
    else:
        content = f"Skill: {skill}"
    return StreamThinkingEvent(
        category="status",
        content=content,
        source=source,
        metadata={"kind": "skill", **info},
    )


def _resolve_agent_label(
    namespace_source: str,
    metadata: dict[str, Any] | None,
    *,
    tool_name: str | None = None,
    active_subagent: str | None = None,
    is_root_graph: bool = True,
) -> str | None:
    """Return a clean agent id (`main` / `*-agent`) suitable for handover UI.

    DeepAgents streams child-agent work under opaque namespaces such as
    ``tools:<uuid>`` / ``model:<uuid>``. Prefer explicit signals in this order:
    tool-name domain map → langgraph node / checkpoint → active task subagent
    → root ``main``.
    """
    inferred = _agent_from_tool_name(tool_name)
    if inferred:
        return inferred

    if metadata:
        node = metadata.get("langgraph_node", "") or ""
        if isinstance(node, str) and (
            node.endswith("-agent") or node.endswith("_subagent")
        ):
            return node
        cp = metadata.get("checkpoint_ns", "") or ""
        if isinstance(cp, str):
            for part in re.split(r"[.:/|]", cp):
                if part.endswith("-agent") or part.endswith("_subagent"):
                    return part
                if part in _KNOWN_SUBAGENTS:
                    return part

    ns = namespace_source or ""
    for part in re.split(r"[.:/|]", ns):
        if part.endswith("-agent") or part.endswith("_subagent") or part in _KNOWN_SUBAGENTS:
            return part

    if not is_root_graph and active_subagent:
        return active_subagent

    if not ns or ns == "main" or is_root_graph:
        # Root-graph model/tools nodes still belong to the main agent
        if is_root_graph and (
            not ns
            or ns == "main"
            or ns.startswith("model")
            or ns.startswith("tools")
            or "Middleware" in ns
        ):
            return "main"
        if not ns or ns == "main":
            return "main"

    if (
        "Middleware" in ns
        or ns.startswith("model")
        or ns.startswith("tools")
        or "after_agent" in ns
        or "before_agent" in ns
    ):
        # Opaque subgraph node without a known domain tool yet
        return active_subagent

    return None


def _display_agent_name(agent: str) -> str:
    """Human-readable label for thinking-step handovers."""
    if agent == "main":
        return "main agent"
    return agent


def _agent_switch_event(agent: str) -> StreamThinkingEvent:
    display = _display_agent_name(agent)
    return StreamThinkingEvent(
        category="status",
        content=f"Current: {display}",
        source=agent,
        metadata={"kind": "agent_switch", "agent": agent},
    )


def _normalize_approval_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a flat ``actions`` list for clients (tool name + args)."""
    raw_requests = payload.get("action_requests") or []
    actions: list[dict[str, Any]] = []
    for req in raw_requests:
        if isinstance(req, dict):
            actions.append(
                {
                    "name": req.get("name") or req.get("tool") or "action",
                    "args": req.get("args") or {},
                }
            )
        else:
            actions.append(
                {
                    "name": getattr(req, "name", None) or "action",
                    "args": getattr(req, "args", None) or {},
                }
            )
    enriched = dict(payload)
    enriched["actions"] = actions
    return enriched


def _format_tool_args(args: Any) -> str:
    if isinstance(args, str):
        return args
    if isinstance(args, dict) and not args:
        # Streaming often sends an empty dict chunk before real args arrive;
        # do not turn that into a literal "{}" that blocks later content.
        return ""
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
        subagent = ""
        desc = ""
        if isinstance(args, dict):
            subagent = str(args.get("subagent_type") or "").strip()
            desc = str(args.get("description") or "").strip()
        if subagent and desc:
            content = f"Delegating to {subagent}: {desc[:200]}"
        elif subagent:
            content = f"Delegating to {subagent}"
        else:
            content = f"Delegating to sub-agent: {desc or json.dumps(args, ensure_ascii=False)}"
        return StreamThinkingEvent(
            category="delegation",
            content=content,
            source=source,
            metadata={
                "tool": tool_name,
                "args": args,
                "subagent_type": subagent or None,
            },
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
            if isinstance(payload, dict):
                payload = _normalize_approval_payload(payload)
            else:
                payload = {"raw": str(payload), "actions": []}
            events.append(
                StreamInterruptEvent(
                    interrupt_id=interrupt_id,
                    interrupt_type="approval",
                    payload=payload,
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
    last_agent: str | None = None
    # Child agent currently running via the DeepAgents ``task`` tool.
    # Subgraph stream namespaces are often ``tools:<uuid>``, so we keep this
    # explicitly and also refine it from domain tool names.
    active_subagent: str | None = None
    # Deduplicate skill activation bubbles within one turn
    seen_skills: set[str] = set()

    def _flush_reasoning(src: str) -> None:
        if reasoning_buf:
            logger.info("[reasoning|%s] %s", src, "".join(reasoning_buf))
            reasoning_buf.clear()

    def _force_agent_switch(agent: str | None) -> list[str]:
        nonlocal last_agent, active_subagent
        if not agent or agent == last_agent:
            return []
        last_agent = agent
        active_subagent = None if agent == "main" else agent
        logger.info("[agent_switch] Current: %s", _display_agent_name(agent))
        return [_sse(_agent_switch_event(agent))]

    def _emit_agent_switch(
        ns_source: str,
        metadata: dict[str, Any] | None,
        *,
        tool_name: str | None = None,
        is_root_graph: bool = True,
    ) -> list[str]:
        agent = _resolve_agent_label(
            ns_source,
            metadata,
            tool_name=tool_name,
            active_subagent=active_subagent,
            is_root_graph=is_root_graph,
        )
        return _force_agent_switch(agent)

    def _note_task_subagent(args: Any) -> list[str]:
        """Record handover target when main delegates via ``task``."""
        nonlocal active_subagent
        sub = _parse_subagent_type(args)
        if not sub:
            return []
        active_subagent = sub
        return _force_agent_switch(sub)

    def _note_skill(tool_name: str | None, args: Any, source: str) -> list[str]:
        """Emit a thinking bubble when a skill is activated or assigned."""
        info = _parse_skill_activation(tool_name, args)
        if not info:
            return []
        key = f"{info.get('action')}:{info.get('scope')}:{info.get('skill')}"
        if key in seen_skills:
            return []
        seen_skills.add(key)
        logger.info(
            "[skill|%s] %s %s",
            source,
            info.get("action"),
            info.get("skill"),
        )
        return [_sse(_skill_thinking_event(info, source))]

    def _emit_buffered_tool_args(tc_id: str, source: str) -> list[str]:
        """Emit one consolidated tool_args SSE for a buffered call (if any)."""
        info = pending_tool_calls.get(tc_id)
        if not info or info.get("args_emitted"):
            return []
        args_str = (info.get("args") or "").strip()
        if not args_str or args_str in ("{}", "null"):
            return []
        info["args_emitted"] = True
        logger.info("[tool_args|%s] %s", source, args_str[:800])
        events = [_sse(StreamToolArgsEvent(args=args_str))]
        tool_name = info.get("name") or ""
        if tool_name == "task":
            events.extend(_note_task_subagent(args_str))
        skill_info = _parse_skill_activation(tool_name, args_str)
        if skill_info:
            info["skill"] = skill_info
            events.extend(_note_skill(tool_name, args_str, source))
        return events

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
                meta_dict = metadata if isinstance(metadata, dict) else None
                if _is_internal_llm_run(meta_dict):
                    continue

                # Entering a subgraph without a resolved name yet still means
                # a child agent is active if we already know it from ``task``.
                for switch_sse in _emit_agent_switch(
                    source,
                    meta_dict,
                    is_root_graph=is_root_graph,
                ):
                    yield switch_sse

                display_source = (
                    _resolve_agent_label(
                        source,
                        meta_dict,
                        active_subagent=active_subagent,
                        is_root_graph=is_root_graph,
                    )
                    or _source_from_metadata(meta_dict)
                    or source
                )

                if isinstance(msg_chunk, (AIMessageChunk, AIMessage)):
                    reasoning = _extract_reasoning(msg_chunk)
                    if reasoning:
                        reasoning_buf.append(reasoning)
                        yield _sse(
                            StreamReasoningEvent(
                                content=reasoning, source=display_source
                            )
                        )
                        yield _sse(
                            StreamThinkingEvent(
                                category="reasoning",
                                content=reasoning,
                                source=display_source,
                                metadata={"kind": "model_reasoning"},
                            )
                        )

                    text = _extract_visible_text(msg_chunk)
                    # Only root-graph assistant text goes to the chat bubble.
                    # Subgraph (sub-agent) narration stays out of the user reply;
                    # tool_result / thinking events still cover the under-the-hood story.
                    if text and is_root_graph:
                        full_response += text
                        yield _sse(
                            StreamTokenEvent(content=text, source=display_source)
                        )

                    if hasattr(msg_chunk, "tool_call_chunks") and msg_chunk.tool_call_chunks:
                        for tc in msg_chunk.tool_call_chunks:
                            tc_id, name, chunk_args = _normalize_tool_call(tc)
                            if name and tc_id not in pending_tool_calls:
                                _flush_reasoning(display_source)
                                for switch_sse in _emit_agent_switch(
                                    source,
                                    meta_dict,
                                    tool_name=name,
                                    is_root_graph=is_root_graph,
                                ):
                                    yield switch_sse
                                tool_source = (
                                    _resolve_agent_label(
                                        source,
                                        meta_dict,
                                        tool_name=name,
                                        active_subagent=active_subagent,
                                        is_root_graph=is_root_graph,
                                    )
                                    or display_source
                                )
                                pending_tool_calls[tc_id] = {
                                    "name": name,
                                    "args": "",
                                    "args_emitted": False,
                                }
                                logger.info("[tool_start|%s] %s", tool_source, name)
                                yield _sse(
                                    StreamToolStartEvent(
                                        tool_call_id=tc_id,
                                        tool_name=name,
                                        source=tool_source,
                                    )
                                )
                                yield _sse(
                                    StreamThinkingEvent(
                                        category="tool",
                                        content=f"Calling tool: {name}",
                                        source=tool_source,
                                        metadata={"tool": name},
                                    )
                                )
                            # Buffer arg fragments; emit once when the call completes.
                            if chunk_args and tc_id in pending_tool_calls:
                                pending_tool_calls[tc_id]["args"] += _format_tool_args(
                                    chunk_args
                                )
                                pending_args = pending_tool_calls[tc_id]["args"]
                                pending_name = pending_tool_calls[tc_id]["name"]
                                chunk_source = (
                                    _resolve_agent_label(
                                        source,
                                        meta_dict,
                                        tool_name=pending_name,
                                        active_subagent=active_subagent,
                                        is_root_graph=is_root_graph,
                                    )
                                    or display_source
                                )
                                if pending_name == "task":
                                    for switch_sse in _note_task_subagent(pending_args):
                                        yield switch_sse
                                skill_info = _parse_skill_activation(
                                    pending_name, pending_args
                                )
                                if skill_info:
                                    pending_tool_calls[tc_id]["skill"] = skill_info
                                    for skill_sse in _note_skill(
                                        pending_name, pending_args, chunk_source
                                    ):
                                        yield skill_sse

                    if isinstance(msg_chunk, AIMessage) and msg_chunk.tool_calls:
                        for tc in msg_chunk.tool_calls:
                            tc_id, name, args = _normalize_tool_call(tc)
                            if not name:
                                continue
                            args_str = _format_tool_args(args)
                            for switch_sse in _emit_agent_switch(
                                source,
                                meta_dict,
                                tool_name=name,
                                is_root_graph=is_root_graph,
                            ):
                                yield switch_sse
                            tool_source = (
                                _resolve_agent_label(
                                    source,
                                    meta_dict,
                                    tool_name=name,
                                    active_subagent=active_subagent,
                                    is_root_graph=is_root_graph,
                                )
                                or display_source
                            )
                            if tc_id not in pending_tool_calls:
                                _flush_reasoning(tool_source)
                                pending_tool_calls[tc_id] = {
                                    "name": name,
                                    "args": args_str,
                                    "args_emitted": False,
                                }
                                logger.info("[tool_start|%s] %s", tool_source, name)
                                yield _sse(
                                    StreamToolStartEvent(
                                        tool_call_id=tc_id,
                                        tool_name=name,
                                        source=tool_source,
                                    )
                                )
                                yield _sse(
                                    _thinking_for_tool(name, args, tool_source)
                                )
                                if name == "task":
                                    for switch_sse in _note_task_subagent(args):
                                        yield switch_sse
                                skill_info = _parse_skill_activation(name, args)
                                if skill_info:
                                    pending_tool_calls[tc_id]["skill"] = skill_info
                                    for skill_sse in _note_skill(
                                        name, args, tool_source
                                    ):
                                        yield skill_sse
                            elif args_str:
                                pending_tool_calls[tc_id]["args"] = args_str
                                if name == "task":
                                    for switch_sse in _note_task_subagent(args_str):
                                        yield switch_sse
                                skill_info = _parse_skill_activation(name, args_str)
                                if skill_info:
                                    pending_tool_calls[tc_id]["skill"] = skill_info
                                    for skill_sse in _note_skill(
                                        name, args_str, tool_source
                                    ):
                                        yield skill_sse
                            for event in _emit_buffered_tool_args(tc_id, tool_source):
                                yield event

                elif isinstance(msg_chunk, ToolMessage):
                    _flush_reasoning(display_source)
                    tc_id = getattr(msg_chunk, "tool_call_id", None) or ""
                    if tc_id:
                        for event in _emit_buffered_tool_args(str(tc_id), display_source):
                            yield event
                    else:
                        # Fallback: flush oldest un-emitted buffered args
                        for pending_id, info in pending_tool_calls.items():
                            if not info.get("args_emitted") and info.get("args"):
                                for event in _emit_buffered_tool_args(
                                    pending_id, display_source
                                ):
                                    yield event
                                break

                    result_text = (
                        msg_chunk.content
                        if isinstance(msg_chunk.content, str)
                        else json.dumps(msg_chunk.content, ensure_ascii=False)
                    )
                    tool_name = msg_chunk.name or "tool"

                    # Infer child agent from domain tools or skill-path ls results
                    for switch_sse in _emit_agent_switch(
                        source,
                        meta_dict,
                        tool_name=tool_name,
                        is_root_graph=is_root_graph,
                    ):
                        yield switch_sse
                    if tool_name == "ls":
                        skills_agent = _agent_from_skills_path(result_text)
                        if skills_agent:
                            for switch_sse in _force_agent_switch(skills_agent):
                                yield switch_sse

                    tool_source = (
                        _resolve_agent_label(
                            source,
                            meta_dict,
                            tool_name=tool_name,
                            active_subagent=active_subagent,
                            is_root_graph=is_root_graph,
                        )
                        or display_source
                    )

                    pending_info = (
                        pending_tool_calls.get(str(tc_id)) if tc_id else None
                    ) or {}
                    skill_info = pending_info.get("skill") or _parse_skill_activation(
                        tool_name, pending_info.get("args")
                    )
                    if skill_info:
                        for skill_sse in _note_skill(
                            tool_name, pending_info.get("args") or skill_info, tool_source
                        ):
                            yield skill_sse
                        # Avoid dumping the full SKILL.md into the thinking UI
                        if tool_name in ("read_file", "read_file_tool"):
                            result_text = (
                                f"Loaded skill `{skill_info.get('skill')}` "
                                f"from {skill_info.get('path') or 'SKILL.md'}"
                            )

                    logger.info(
                        "[tool_result|%s] %s: %s",
                        tool_source,
                        tool_name,
                        result_text[:500],
                    )
                    yield _sse(
                        StreamToolResultEvent(
                            tool_name=tool_name,
                            result=result_text[:4000],
                            source=tool_source,
                        )
                    )
                    yield _sse(
                        StreamThinkingEvent(
                            category="tool",
                            content=f"Tool completed: {tool_name}",
                            source=tool_source,
                            metadata={"result_preview": result_text[:500]},
                        )
                    )

                    # ``task`` returned to the main agent — hand control back
                    if tool_name == "task" and is_root_graph:
                        for switch_sse in _force_agent_switch("main"):
                            yield switch_sse

            elif mode == "updates":
                for switch_sse in _emit_agent_switch(
                    source, None, is_root_graph=is_root_graph
                ):
                    yield switch_sse
                if not isinstance(data, dict):
                    continue
                plan_source = (
                    _resolve_agent_label(
                        source,
                        None,
                        active_subagent=active_subagent,
                        is_root_graph=is_root_graph,
                    )
                    or source
                )
                for _node, update in data.items():
                    if not isinstance(update, dict):
                        continue
                    todos = update.get("todos")
                    if todos is not None:
                        _flush_reasoning(plan_source)
                        summary = ", ".join(
                            f"[{t.get('status', '?')}] {t.get('content', '')}" for t in todos
                        )
                        logger.info("[plan|%s] %s", plan_source, summary)
                        yield _sse(StreamPlanEvent(todos=todos, source=plan_source))
                        yield _sse(
                            StreamThinkingEvent(
                                category="plan",
                                content=f"Plan updated: {summary}",
                                source=plan_source,
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
