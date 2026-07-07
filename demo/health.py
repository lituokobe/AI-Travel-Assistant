"""Health checks for demo infrastructure."""

from __future__ import annotations

import socket
import sqlite3
from pathlib import Path

import pymongo
import redis

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "mcp_server" / "travel_new.sqlite"


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_redis(uri: str = "redis://localhost:6379") -> tuple[bool, str]:
    try:
        client = redis.from_url(uri, socket_connect_timeout=2)
        client.ping()
        return True, "Redis OK"
    except Exception as exc:
        return False, f"Redis unavailable: {exc}"


def check_mongodb(uri: str = "mongodb://localhost:27017") -> tuple[bool, str]:
    try:
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
        return True, "MongoDB OK"
    except Exception as exc:
        return False, f"MongoDB unavailable: {exc}"


def check_database() -> tuple[bool, str]:
    if not DB_PATH.exists():
        return False, f"SQLite DB missing: {DB_PATH}"
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM flights")
        count = cur.fetchone()[0]
        conn.close()
        return count > 0, f"SQLite OK ({count} flights)"
    except Exception as exc:
        return False, f"SQLite error: {exc}"


def check_mcp(host: str = "127.0.0.1", port: int = 8000) -> tuple[bool, str]:
    if _port_open(host, port):
        return True, f"MCP server listening on {host}:{port}"
    return False, f"MCP server not reachable on {host}:{port}"


def check_api(host: str = "127.0.0.1", port: int = 8080) -> tuple[bool, str]:
    if _port_open(host, port):
        return True, f"API server listening on {host}:{port}"
    return False, f"API server not reachable on {host}:{port}"


def run_all_checks() -> list[tuple[str, bool, str]]:
    results = []
    for name, ok, msg in [
        ("database", *check_database()),
        ("redis", *check_redis()),
        ("mongodb", *check_mongodb()),
        ("mcp", *check_mcp()),
        ("api", *check_api()),
    ]:
        results.append((name, ok, msg))
    return results
