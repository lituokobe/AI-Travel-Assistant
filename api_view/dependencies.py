"""FastAPI dependencies."""

from fastapi import Header, HTTPException

from api_view.agent_loader import lifecycle_manager
from api_view.config import DEFAULT_PASSENGER_ID, DEFAULT_USER_ID, DEFAULT_USERNAME
from api_view.models.requests import UserContext


async def require_agent_ready() -> None:
    if not lifecycle_manager.is_ready:
        raise HTTPException(
            status_code=503,
            detail="Agent is not initialized. POST /api/v1/agent/initialize first.",
        )


def resolve_user_context(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_username: str | None = Header(None, alias="X-Username"),
    x_passenger_id: str | None = Header(None, alias="X-Passenger-Id"),
) -> UserContext:
    return UserContext(
        user_id=x_user_id or DEFAULT_USER_ID,
        username=x_username or DEFAULT_USERNAME,
        passenger_id=x_passenger_id or DEFAULT_PASSENGER_ID,
    )
