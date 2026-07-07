"""Health check endpoints."""

from fastapi import APIRouter

from agent.config import MONGODB_URI, REDIS_URI
from api_view.agent_loader import lifecycle_manager

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Liveness probe."""
    return {"status": "ok", "agent_state": lifecycle_manager.state.value}


@router.get("/health/ready")
async def readiness_check():
    """Readiness probe — verifies agent and backing services."""
    checks = {
        "agent": lifecycle_manager.is_ready,
        "redis_uri": REDIS_URI,
        "mongodb_uri": MONGODB_URI,
    }
    ready = checks["agent"]
    return {
        "ready": ready,
        "checks": checks,
    }
