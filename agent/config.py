from datetime import timedelta

import httpx
import pymongo

from langchain_openai import ChatOpenAI
import os
from pathlib import Path
from dotenv import load_dotenv
from langgraph.checkpoint.redis import RedisSaver
from langgraph.store.mongodb import MongoDBStore

from opensandbox.config import ConnectionConfigSync

# ---------- path config ----------
# Get project folder dir
current_file = Path(__file__).resolve()
project_dir = current_file.parent.parent

# Define the paths
ENV_PATH = project_dir / ".env"
LOG_PATH = project_dir / "logs"
# Sandbox skills root path
SANDBOX_SKILLS_ROOT = "/skills"
# Sandbox memories root path (where user private memories are stored)
SANDBOX_MEMORIES_ROOT = "/memories"
# Sandbox directory for intermediate analysis files
SANDBOX_ANALYSIS_ROOT = "/analysis"
# Sandbox directory for data files
SANDBOX_DATA_ROOT = "/data"
# Local skills resource directory (path within the project, relative to the project root)
LOCAL_SKILLS_DIR = project_dir / "skills"
# Local download directory (destination path for files downloaded from the sandbox)
DOWNLOAD_DIR = project_dir / "download"
# Local sub-agent configuration directory
LOCAL_SUBAGENT_CONFIG_DIR = project_dir / "agent/subagents"
# Agent memory file on the local drive
LOCAL_AGENTS_MD = project_dir / "agent/memory/AGENTS.md"

# ---------- Filename constants ----------
# Main agent read-only guide file (uploaded to sandbox /AGENTS.md)
AGENTS_MD_FILENAME = "/AGENTS.md"
# User preferences filename (under /memories/{user_id}/)
USER_PREFERENCES_FILENAME = "preferences.md"

# ---------- LLM config ----------
load_dotenv(ENV_PATH, override=True)

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
ZHIPU_API_KEY = os.getenv('ZHIPU_API_KEY')
ALIBABA_API_KEY = os.getenv('ALIBABA_API_KEY')

ALIBABA_BASE_URL = os.getenv('ALIBABA_BASE_URL')
OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL')
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL')
ZHIPU_BASE_URL = os.getenv('ZHIPU_BASE_URL')

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# main agent LLM
MAIN_MODEL = ChatOpenAI(
    model="deepseek-v4-pro",
    temperature=1.1,
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    max_tokens=2560000,
    model_kwargs={
        "extra_body": {
            "thinking": {"type": "disabled"}
        }
    }
)

# LLM for summarization
SUMMARY_MODEL = ChatOpenAI(
    model="deepseek-v4-flash",
    temperature=0.3,
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    max_tokens=2560000,
    model_kwargs={
        "extra_body": {
            "thinking": {"type": "disabled"}
        }
    }
)

# ---------- Sandbox config ----------
# OpenSandbox connection
SANDBOX_CONFIG = ConnectionConfigSync(
    domain="http://47.99.102.45:8080",#"http://39.100.100.28:8080",
    use_server_proxy=True,
    request_timeout=timedelta(seconds=60),
    transport=httpx.HTTPTransport(limits=httpx.Limits(max_connections=20)),
)

# ---------- constant config ----------
LOG_KEEPING_HOURS = 24
LOG_PREFIX = "travel_assistant"

# ---------- persistence ----------
MONGODB_URI = "mongodb://localhost:27017"
MONGODB_DB_NAME = "mongodb_db_travel_assistant"
MONGODB_COLLECTION = "mongodb_collection_travel_assistant"
REDIS_URI = "redis://localhost:6379"

# MongoDB for Store (long term memory).
mongo_client = pymongo.MongoClient(MONGODB_URI)
db = mongo_client[MONGODB_DB_NAME]
collection = db[MONGODB_COLLECTION] # only pointers are created

STORE = MongoDBStore(collection=collection)

# Redis for checkpoint (short term memory).
CHECKPOINTER = RedisSaver()
CHECKPOINTER.configure_client(redis_url=REDIS_URI)
CHECKPOINTER.setup()

# ---------- user skill persistence ----------
PERSISTED_SKILLS_ROOT = "/persisted-skills"
SKILLS_STORE_NAMESPACE = ("skills",)
SCOPE_MAP = {
    "main": "main",
    "car-agent": "car",
    "flights-agent": "flights",
    "hotels-agent": "hotels",
    "activity-agent": "activity"
}