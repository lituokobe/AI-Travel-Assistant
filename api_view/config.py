"""API layer configuration — isolated from agent/config.py."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env", override=True)

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))
API_PREFIX = "/api/v1"

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "mongodb_db_travel_assistant")
SESSIONS_COLLECTION = os.getenv("API_SESSIONS_COLLECTION", "api_sessions")

DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "user-001")
DEFAULT_USERNAME = os.getenv("DEFAULT_USERNAME", "Demo User")
DEFAULT_PASSENGER_ID = os.getenv("DEFAULT_PASSENGER_ID", "3442 587679")

GRADIO_HOST = os.getenv("GRADIO_HOST", "0.0.0.0")
GRADIO_PORT = int(os.getenv("GRADIO_PORT", "7860"))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://127.0.0.1:{API_PORT}")

ENABLE_MODEL_THINKING = os.getenv("ENABLE_MODEL_THINKING", "true").lower() in (
    "1",
    "true",
    "yes",
)
