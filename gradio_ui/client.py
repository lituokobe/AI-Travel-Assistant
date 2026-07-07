"""HTTP client for the Travel Assistant API."""

from __future__ import annotations

import json
from typing import Any, Iterator
import httpx

from api_view.config import API_BASE_URL, DEFAULT_PASSENGER_ID, DEFAULT_USER_ID, DEFAULT_USERNAME


class TravelAPIClient:
    def __init__(self, base_url: str = API_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def _headers(self, user_id: str, username: str, passenger_id: str) -> dict[str, str]:
        return {
            "X-User-Id": user_id,
            "X-Username": username,
            "X-Passenger-Id": passenger_id,
            "Content-Type": "application/json",
        }

    def agent_status(self) -> dict[str, Any]:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{self.base_url}/api/v1/agent/status")
            resp.raise_for_status()
            return resp.json()

    def initialize_agent(self) -> dict[str, Any]:
        with httpx.Client(timeout=300) as client:
            resp = client.post(f"{self.base_url}/api/v1/agent/initialize")
            resp.raise_for_status()
            return resp.json()

    def chat(
        self,
        message: str,
        thread_id: str | None,
        *,
        user_id: str = DEFAULT_USER_ID,
        username: str = DEFAULT_USERNAME,
        passenger_id: str = DEFAULT_PASSENGER_ID,
    ) -> dict[str, Any]:
        payload = {"message": message, "thread_id": thread_id}
        with httpx.Client(timeout=300) as client:
            resp = client.post(
                f"{self.base_url}/api/v1/chat",
                json=payload,
                headers=self._headers(user_id, username, passenger_id),
            )
            resp.raise_for_status()
            return resp.json()

    def stream_chat(
        self,
        message: str,
        thread_id: str | None,
        *,
        user_id: str = DEFAULT_USER_ID,
        username: str = DEFAULT_USERNAME,
        passenger_id: str = DEFAULT_PASSENGER_ID,
    ) -> Iterator[dict[str, Any]]:
        payload = {"message": message, "thread_id": thread_id}
        with httpx.Client(timeout=300) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/api/v1/chat/stream",
                json=payload,
                headers=self._headers(user_id, username, passenger_id),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        yield json.loads(line[6:])

    def resume(
        self,
        thread_id: str,
        resume_value: Any,
        *,
        user_id: str = DEFAULT_USER_ID,
        username: str = DEFAULT_USERNAME,
        passenger_id: str = DEFAULT_PASSENGER_ID,
    ) -> dict[str, Any]:
        payload = {
            "thread_id": thread_id,
            "resume_value": resume_value,
            "user": {
                "user_id": user_id,
                "username": username,
                "passenger_id": passenger_id,
            },
        }
        with httpx.Client(timeout=300) as client:
            resp = client.post(f"{self.base_url}/api/v1/chat/resume", json=payload)
            resp.raise_for_status()
            return resp.json()

    def stream_resume(
        self,
        thread_id: str,
        resume_value: Any,
        *,
        user_id: str = DEFAULT_USER_ID,
        username: str = DEFAULT_USERNAME,
        passenger_id: str = DEFAULT_PASSENGER_ID,
    ) -> Iterator[dict[str, Any]]:
        payload = {
            "thread_id": thread_id,
            "resume_value": resume_value,
            "user": {
                "user_id": user_id,
                "username": username,
                "passenger_id": passenger_id,
            },
        }
        with httpx.Client(timeout=300) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/api/v1/chat/resume/stream",
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        yield json.loads(line[6:])
