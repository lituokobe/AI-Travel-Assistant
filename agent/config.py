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
from pymongo import MongoClient
from pymongo.synchronous.collection import Collection

# ---------- path config ----------
# Get project folder dir
current_file = Path(__file__).resolve()
project_dir = current_file.parent.parent

# Define the paths
ENV_PATH = project_dir / ".env"
LOG_PATH = project_dir / "logs"
# 沙箱内技能根路径
SANDBOX_SKILLS_ROOT = "/skills"
# 沙箱内记忆根路径（用户私有记忆存放处）
SANDBOX_MEMORIES_ROOT = "/memories"
# 沙箱内分析中间文件存放目录
SANDBOX_ANALYSIS_ROOT = "/analysis"
# 沙箱内数据文件存放目录
SANDBOX_DATA_ROOT = "/data"
# 本地技能资源目录（项目内的路径，相对于项目根）
LOCAL_SKILLS_DIR = project_dir / "skills"
# 本地下载目录（从沙箱下载文件的目标路径）
DOWNLOAD_DIR = project_dir / "download"
# 本地子 Agent 配置目录
LOCAL_SUBAGENT_CONFIG_DIR = project_dir / "agent/subagents"
# Agent memory file on the local drive
LOCAL_AGENTS_MD = project_dir / "agent/memory/AGENTS.md"

# ---------- Filename constants ----------
# 主 Agent 只读指引文件（上传到沙箱 /AGENTS.md）
AGENTS_MD_FILENAME = "/AGENTS.md"
# 用户偏好文件名（在 /memories/{user_id}/ 下）
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
    "trip-agent": "trip"
}