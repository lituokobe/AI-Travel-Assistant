"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_view.agent_loader import lifecycle_manager
from api_view.api import chat, health, lifecycle, sessions
from api_view.config import API_PREFIX


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Auto-initialize agent on startup."""
    try:
        await lifecycle_manager.initialize()
    except Exception:
        pass
    yield
    await lifecycle_manager.shutdown()


app = FastAPI(
    title="AI Travel Assistant API",
    description="Production-grade API for the AI Travel Assistant agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(lifecycle.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(sessions.router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {
        "service": "AI Travel Assistant API",
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
    }
