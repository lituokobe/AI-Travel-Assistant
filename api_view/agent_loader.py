"""Agent lifecycle management for the API layer."""

from __future__ import annotations

import asyncio
import time
import uuid
from enum import Enum
from typing import Any

from langchain_core.runnables import RunnableConfig

from agent.main_agent import create_main_agent
from agent.schema import TravelContext
from api_view.config import DEFAULT_PASSENGER_ID


class AgentState(str, Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"


class AgentLifecycleManager:
    """Manages agent initialization, status, and graceful shutdown."""

    def __init__(self) -> None:
        self._agent: Any | None = None
        self._state = AgentState.UNINITIALIZED
        self._error: str | None = None
        self._init_started_at: float | None = None
        self._ready_at: float | None = None
        self._sandbox_id: str | None = None
        self._model_info: dict | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def agent(self) -> Any:
        if self._agent is None:
            raise RuntimeError(f"Agent not ready (state={self._state.value})")
        return self._agent

    @property
    def is_ready(self) -> bool:
        return self._state == AgentState.READY and self._agent is not None

    async def initialize(self, *, sandbox_id: str | None = None) -> dict[str, Any]:
        async with self._lock:
            if self._state == AgentState.READY:
                return self.status()

            self._state = AgentState.INITIALIZING
            self._error = None
            self._init_started_at = time.time()
            self._sandbox_id = sandbox_id

            try:
                from api_view.db_bootstrap import sync_database_dates
                from api_view.model_override import apply_model_overrides

                sync_database_dates()
                model_info = apply_model_overrides()
                self._agent = await create_main_agent(sandbox_id=sandbox_id)
                self._state = AgentState.READY
                self._ready_at = time.time()
                self._model_info = model_info
            except Exception as exc:
                self._state = AgentState.ERROR
                self._error = str(exc)
                self._agent = None
                raise

            return self.status()

    async def ensure_ready(self) -> Any:
        if self.is_ready:
            return self._agent

        if self._state == AgentState.UNINITIALIZED:
            await self.initialize()

        if not self.is_ready:
            raise RuntimeError(self._error or f"Agent not ready (state={self._state.value})")
        return self._agent

    async def shutdown(self) -> dict[str, Any]:
        async with self._lock:
            self._state = AgentState.SHUTTING_DOWN
            self._agent = None
            self._state = AgentState.UNINITIALIZED
            self._ready_at = None
            self._init_started_at = None
            return {"status": "shutdown", "message": "Agent released"}

    def status(self) -> dict[str, Any]:
        uptime = None
        if self._ready_at:
            uptime = round(time.time() - self._ready_at, 2)

        init_duration = None
        if self._init_started_at and self._ready_at:
            init_duration = round(self._ready_at - self._init_started_at, 2)

        return {
            "state": self._state.value,
            "ready": self.is_ready,
            "error": self._error,
            "sandbox_id": self._sandbox_id,
            "uptime_seconds": uptime,
            "init_duration_seconds": init_duration,
            "model": self._model_info,
        }


lifecycle_manager = AgentLifecycleManager()


def new_thread_id() -> str:
    return str(uuid.uuid4())


def create_config(
    thread_id: str,
    *,
    passenger_id: str | None = None,
) -> RunnableConfig:
    """Build LangGraph RunnableConfig for a conversation thread."""
    return {
        "configurable": {
            "thread_id": thread_id,
            "passenger_id": passenger_id or DEFAULT_PASSENGER_ID,
        }
    }


def create_travel_context(user_id: str, username: str) -> TravelContext:
    return TravelContext(user_id=user_id, username=username)
