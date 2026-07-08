"""Shared pytest fixtures and import-time mocks for agent.config."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("REDIS_URI", "redis://localhost:6379")
os.environ.setdefault("SANDBOX_DOMAIN", "http://test-sandbox:8080")

# Patch persistence backends before agent.config is imported by test modules.
_mock_redis = MagicMock()
_mock_redis.configure_client = MagicMock()
_mock_redis.setup = MagicMock()
_redis_patcher = patch("langgraph.checkpoint.redis.RedisSaver", return_value=_mock_redis)
_redis_patcher.start()

_mock_mongo_client = MagicMock()
_mock_mongo_db = MagicMock()
_mock_mongo_client.__getitem__ = MagicMock(return_value=_mock_mongo_db)
_mongo_patcher = patch("pymongo.MongoClient", return_value=_mock_mongo_client)
_mongo_patcher.start()

import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def sample_user_context():
    from api_view.models.requests import UserContext

    return UserContext(
        user_id="test-user",
        username="Test User",
        passenger_id="3442 587679",
    )


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={"messages": []})
    agent.aget_state = AsyncMock(return_value=MagicMock(interrupts=[]))
    return agent


@pytest.fixture
def fresh_lifecycle_manager():
    from api_view.agent_loader import AgentLifecycleManager

    return AgentLifecycleManager()
