"""Tests for session metadata service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from api_view.services import session_service


def test_ensure_session_inserts_when_missing():
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = None

    with patch.object(session_service, "_sessions", mock_collection):
        session_service.ensure_session("t1", "user-1", "Find flights to NYC")

    mock_collection.insert_one.assert_called_once()
    doc = mock_collection.insert_one.call_args[0][0]
    assert doc["thread_id"] == "t1"
    assert doc["user_id"] == "user-1"
    assert "NYC" in doc["title"]


def test_ensure_session_skips_existing():
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {"thread_id": "t1"}

    with patch.object(session_service, "_sessions", mock_collection):
        session_service.ensure_session("t1", "user-1", "hello")

    mock_collection.insert_one.assert_not_called()


def test_list_sessions_returns_paginated_response():
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 1
    now = datetime.now(timezone.utc)
    mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = [
        {
            "thread_id": "t1",
            "title": "Flights",
            "created_at": now,
            "updated_at": now,
            "message_count": 3,
        }
    ]

    with patch.object(session_service, "_sessions", mock_collection):
        result = session_service.list_sessions("user-1", page=1, limit=10)

    assert result.total == 1
    assert len(result.sessions) == 1
    assert result.sessions[0].thread_id == "t1"


def test_delete_session():
    mock_collection = MagicMock()
    mock_collection.delete_one.return_value = MagicMock(deleted_count=1)

    with (
        patch.object(session_service, "_sessions", mock_collection),
        patch.object(session_service, "CHECKPOINTER") as checkpointer,
    ):
        deleted = session_service.delete_session("t1")

    assert deleted is True
    checkpointer.delete_thread.assert_called_once_with("t1")
