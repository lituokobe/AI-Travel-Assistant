#!/usr/bin/env python3
"""
Unified demo launcher for AI Travel Assistant.

Starts (in order):
  1. Synchronizes SQLite travel DB dates (data/data_base)
  2. MCP tool server  (port 8000)
  3. FastAPI agent API (port 8080)
  4. Gradio chat UI    (port 7860)

Usage:
  python demo/run_demo.py
  python demo/run_demo.py --skip-ui        # API + MCP only
  python demo/run_demo.py --sync-db-only  # only refresh DB dates
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
    parser.add_argument("--sync-db-only", action="store_true", help="Only sync database dates")
    parser.add_argument("--no-db-sync", action="store_true", help="Skip database date sync")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    sys.path.insert(0, str(PROJECT_DIR))

    env_file = PROJECT_DIR / ".env"
    if not env_file.exists():
        example = PROJECT_DIR / "env.example"
        _log(f"WARNING: .env not found. Copy {example.name} to .env and add your API keys.")
    else:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=True)

    if not args.no_db_sync:
        from api_view.db_bootstrap import sync_database_dates

        _log("Synchronizing travel database dates...")
        db_path = sync_database_dates()
        _log(f"Database ready: {db_path}")

    if args.sync_db_only:
        return

    from demo.health import check_mongodb, check_redis

    redis_ok, redis_msg = check_redis()
    mongo_ok, mongo_msg = check_mongodb()
    _log(redis_msg)
    _log(mongo_msg)

    if not redis_ok or not mongo_ok:
        _log("")
        _log("Infrastructure not ready. Ensure Redis and MongoDB are running:")
        _log("  Redis:   localhost:6379")
        _log("  MongoDB: localhost:27017")
        _log("")
        if not redis_ok:
            sys.exit(1)

    mcp_proc = _start_process("mcp", [PYTHON, "-m", "mcp_server.server_main"])
    if not _wait_for_port("127.0.0.1", 8000, timeout=30, label="MCP server"):
        _log("MCP server failed to start.")
        _shutdown()
        return

    api_proc = _start_process("api", [PYTHON, "-m", "api_view.run"])
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

    ui_proc = _start_process("ui", [PYTHON, "-m", "gradio_ui.run"])
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
