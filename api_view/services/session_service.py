"""Session metadata and checkpoint-backed history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pymongo
from langchain_core.messages import BaseMessage, messages_from_dict

from agent.config import CHECKPOINTER
from agent.schema import Message, Session, SessionListResponse, SessionMessagesResponse
from api_view.config import MONGODB_DB_NAME, MONGODB_URI, SESSIONS_COLLECTION
from api_view.services.message_converter import langchain_to_api_message

_mongo = pymongo.MongoClient(MONGODB_URI)
_sessions = _mongo[MONGODB_DB_NAME][SESSIONS_COLLECTION]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_doc(
    thread_id: str,
    user_id: str,
    title: str,
    *,
    message_count: int = 0,
) -> dict[str, Any]:
    now = _now()
    return {
        "thread_id": thread_id,
        "user_id": user_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "message_count": message_count,
    }


def ensure_session(thread_id: str, user_id: str, first_message: str) -> None:
    """Create session metadata if it does not exist."""
    existing = _sessions.find_one({"thread_id": thread_id})
    if existing:
        return

    title = first_message[:80].strip() or "New conversation"
    _sessions.insert_one(_session_doc(thread_id, user_id, title))


def touch_session(thread_id: str, *, delta_messages: int = 1) -> None:
    _sessions.update_one(
        {"thread_id": thread_id},
        {
            "$set": {"updated_at": _now()},
            "$inc": {"message_count": delta_messages},
        },
    )


def list_sessions(
    user_id: str,
    *,
    page: int = 1,
    limit: int = 20,
) -> SessionListResponse:
    skip = max(page - 1, 0) * limit
    query = {"user_id": user_id}
    total = _sessions.count_documents(query)
    cursor = (
        _sessions.find(query)
        .sort("updated_at", pymongo.DESCENDING)
        .skip(skip)
        .limit(limit)
    )

    sessions: list[Session] = []
    for doc in cursor:
        sessions.append(
            Session(
                thread_id=doc["thread_id"],
                title=doc.get("title", "Conversation"),
                created_at=doc.get("created_at", _now()),
                updated_at=doc.get("updated_at", _now()),
                message_count=doc.get("message_count", 0),
            )
        )

    return SessionListResponse(sessions=sessions, total=total, page=page, limit=limit)


def _deserialize_checkpoint_messages(raw_messages: list[Any]) -> list[BaseMessage]:
    if not raw_messages:
        return []
    if isinstance(raw_messages[0], BaseMessage):
        return raw_messages
    try:
        return messages_from_dict(raw_messages)
    except Exception:
        return []


def get_session_messages(thread_id: str) -> SessionMessagesResponse:
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = CHECKPOINTER.get_tuple(config)
    messages: list[Message] = []

    if checkpoint and checkpoint.checkpoint:
        channel_values = checkpoint.checkpoint.get("channel_values", {})
        raw_messages = channel_values.get("messages", [])
        for msg in _deserialize_checkpoint_messages(raw_messages):
            messages.append(langchain_to_api_message(msg))

    return SessionMessagesResponse(thread_id=thread_id, messages=messages)


def delete_session(thread_id: str) -> bool:
    CHECKPOINTER.delete_thread(thread_id)
    result = _sessions.delete_one({"thread_id": thread_id})
    return result.deleted_count > 0
