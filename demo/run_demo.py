#!/usr/bin/env python3
"""
Unified demo launcher for AI Travel Assistant.

Starts (in order):
  1. Seeds SQLite demo database (if missing)
  2. MCP tool server  (port 8000)
  3. FastAPI agent API (port 8080)
  4. Gradio chat UI    (port 7860)

Usage:
  python demo/run_demo.py
  python demo/run_demo.py --skip-ui        # API + MCP only
  python demo/run_demo.py --seed-only      # just create the database
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
PYTHON = str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable)

_processes: list[subprocess.Popen] = []


def _log(msg: str) -> None:
    print(f"[demo] {msg}", flush=True)


def _wait_for_port(host: str, port: int, timeout: float = 120.0, label: str = "") -> bool:
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                _log(f"{label or f'{host}:{port}'} is ready")
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _start_process(name: str, cmd: list[str], env: dict | None = None) -> subprocess.Popen:
    _log(f"Starting {name}: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_DIR),
        env=env or os.environ.copy(),
    )
    _processes.append(proc)
    return proc


def _shutdown(signum=None, frame=None) -> None:
    _log("Shutting down...")
    for proc in reversed(_processes):
        if proc.poll() is None:
            proc.terminate()
    for proc in reversed(_processes):
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    _log("All services stopped.")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Travel Assistant Demo Launcher")
    parser.add_argument("--skip-ui", action="store_true", help="Skip Gradio UI")
    parser.add_argument("--seed-only", action="store_true", help="Only seed the database")
    parser.add_argument("--no-seed", action="store_true", help="Skip database seeding")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Load .env if present
    env_file = PROJECT_DIR / ".env"
    if not env_file.exists():
        example = PROJECT_DIR / "env.example"
        _log(f"WARNING: .env not found. Copy {example.name} to .env and add your API keys.")
    else:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=True)

    # --- Pre-flight checks ---
    sys.path.insert(0, str(PROJECT_DIR))
    from demo.health import check_mongodb, check_redis

    redis_ok, redis_msg = check_redis()
    mongo_ok, mongo_msg = check_mongodb()
    _log(redis_msg)
    _log(mongo_msg)

    if not redis_ok or not mongo_ok:
        _log("")
        _log("Infrastructure not ready. Start Redis and MongoDB first:")
        _log("  docker run -d --name redis -p 6379:6379 -p 8001:8001 \\")
        _log("    -v ./data/redis-data:/data redis/redis-stack:latest")
        _log("  docker run -d --name mongodb -p 27017:27017 \\")
        _log("    -v ./data/mongodb-data:/data/db mongo:latest")
        _log("")
        if not redis_ok:
            sys.exit(1)

    # --- Seed database ---
    if not args.no_seed:
        from demo.seed_database import DB_PATH, seed

        if not DB_PATH.exists() or args.seed_only:
            _log("Seeding demo SQLite database...")
            path = seed()
            _log(f"Database ready: {path}")
        else:
            _log(f"Database exists: {DB_PATH}")

    if args.seed_only:
        return

    # --- Start MCP server ---
    mcp_proc = _start_process(
        "mcp",
        [PYTHON, "-m", "mcp_server.server_main"],
    )
    if not _wait_for_port("127.0.0.1", 8000, timeout=30, label="MCP server"):
        _log("MCP server failed to start. Check output above.")
        _shutdown()
        return

    # --- Start API server ---
    api_proc = _start_process(
        "api",
        [PYTHON, "-m", "api_view.run"],
    )
    if not _wait_for_port("127.0.0.1", 8080, timeout=180, label="API server"):
        _log("API server failed to start (agent init may take 1-2 min).")
        _log("Check logs — ensure DEEPSEEK_API_KEY and TAVILY_API_KEY are set in .env")
        _shutdown()
        return

    _log("API docs: http://localhost:8080/docs")

    if args.skip_ui:
        _log("Running API + MCP. Press Ctrl+C to stop.")
        try:
            while True:
                for proc in _processes:
                    if proc.poll() is not None:
                        _log(f"Process exited with code {proc.returncode}")
                        _shutdown()
                time.sleep(1)
        except KeyboardInterrupt:
            _shutdown()
        return

    # --- Start Gradio UI ---
    ui_proc = _start_process(
        "ui",
        [PYTHON, "-m", "gradio_ui.run"],
    )
    if not _wait_for_port("0.0.0.0", 7860, timeout=60, label="Gradio UI"):
        _log("Gradio UI failed to start.")
        _shutdown()
        return

    _log("")
    _log("=" * 60)
    _log("  Demo is running!")
    _log("  Chat UI:  http://localhost:7860")
    _log("  API docs: http://localhost:8080/docs")
    _log("  MCP:      http://127.0.0.1:8000/mcp")
    _log("=" * 60)
    _log("Press Ctrl+C to stop all services.")
    _log("")

    try:
        while True:
            for proc in _processes:
                if proc.poll() is not None:
                    _log(f"Process exited unexpectedly (code {proc.returncode})")
                    _shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
