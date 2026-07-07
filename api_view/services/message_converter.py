"""Convert LangChain messages to API Message models."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from agent.schema import Message


def _message_id(msg: BaseMessage) -> str:
    return getattr(msg, "id", None) or str(uuid.uuid4())


def _extract_source(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    return metadata.get("langgraph_node") or metadata.get("source")


def langchain_to_api_message(msg: BaseMessage, metadata: dict[str, Any] | None = None) -> Message:
    source = _extract_source(metadata)
    base = {
        "id": _message_id(msg),
        "created_at": datetime.now(),
        "source": source,
    }

    if isinstance(msg, HumanMessage):
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        return Message(role="user", content=content, **base)

    if isinstance(msg, AIMessage):
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "args": tc.get("args", {}),
                }
                for tc in msg.tool_calls
            ]
        return Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            **base,
        )

    if isinstance(msg, ToolMessage):
        text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, ensure_ascii=False)
        return Message(
            role="tool",
            content=text,
            tool_call_id=msg.tool_call_id,
            tool_name=msg.name,
            tool_status="done",
            text=text,
            **base,
        )

    content = msg.content if isinstance(getattr(msg, "content", ""), str) else str(getattr(msg, "content", ""))
    return Message(role=getattr(msg, "type", "unknown"), content=content, **base)


def state_messages_to_api(messages: list[BaseMessage]) -> list[Message]:
    return [langchain_to_api_message(m) for m in messages]
