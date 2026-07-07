"""Agent lifecycle management endpoints."""

from fastapi import APIRouter, HTTPException

from api_view.agent_loader import lifecycle_manager
from api_view.models.requests import AgentInitRequest

router = APIRouter(prefix="/agent", tags=["agent-lifecycle"])


@router.get("/status")
async def agent_status():
    """Return current agent lifecycle state."""
    return lifecycle_manager.status()


@router.post("/initialize")
async def initialize_agent(body: AgentInitRequest | None = None):
    """Initialize (or re-initialize) the travel agent."""
    try:
        sandbox_id = body.sandbox_id if body else None
        return await lifecycle_manager.initialize(sandbox_id=sandbox_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/shutdown")
async def shutdown_agent():
    """Release the agent instance (graceful shutdown for demo)."""
    return await lifecycle_manager.shutdown()
