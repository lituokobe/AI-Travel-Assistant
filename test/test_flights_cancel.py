"""Unit tests for flights_cancel ownership check and cleanup."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastmcp import FastMCP

import mcp_server.tools.flights_tools as flights_mod


def _seed_cancel_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tickets (
            ticket_no TEXT PRIMARY KEY,
            book_ref TEXT,
            passenger_id TEXT
        );
        CREATE TABLE ticket_flights (
            ticket_no TEXT,
            flight_id INTEGER,
            fare_conditions TEXT,
            amount REAL
        );
        CREATE TABLE boarding_passes (
            ticket_no TEXT,
            flight_id INTEGER,
            boarding_no INTEGER,
            seat_no TEXT
        );
        INSERT INTO tickets VALUES ('7240005432906569', 'C46E9F', '3442 587242');
        INSERT INTO ticket_flights VALUES ('7240005432906569', 101, 'Economy', 0);
        INSERT INTO ticket_flights VALUES ('7240005432906569', 102, 'Economy', 0);
        INSERT INTO boarding_passes VALUES ('7240005432906569', 101, 1, '12A');
        """
    )
    conn.commit()
    conn.close()


def _cancel_fn(monkeypatch: pytest.MonkeyPatch, db_path: Path):
    monkeypatch.setattr(flights_mod, "db", str(db_path))
    mcp = FastMCP("flights-cancel-test")
    flights_mod.register_flights_tools(mcp)
    tool = asyncio.run(mcp.get_tool("flights_cancel"))
    return tool.fn


def test_flights_cancel_succeeds_without_flight_id_on_tickets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = tmp_path / "flights.sqlite"
    _seed_cancel_db(db_path)
    cancel = _cancel_fn(monkeypatch, db_path)

    result = cancel(ticket_no="7240005432906569", passenger_id="3442 587242")
    assert "cancelled successfully" in result.lower()

    conn = sqlite3.connect(db_path)
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE ticket_no = ?",
            ("7240005432906569",),
        ).fetchone()[0]
        == 0
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM ticket_flights WHERE ticket_no = ?",
            ("7240005432906569",),
        ).fetchone()[0]
        == 0
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM boarding_passes WHERE ticket_no = ?",
            ("7240005432906569",),
        ).fetchone()[0]
        == 0
    )
    conn.close()


def test_flights_cancel_rejects_wrong_passenger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = tmp_path / "flights.sqlite"
    _seed_cancel_db(db_path)
    cancel = _cancel_fn(monkeypatch, db_path)

    result = cancel(ticket_no="7240005432906569", passenger_id="0000 000000")
    assert "not the owner" in result.lower()

    conn = sqlite3.connect(db_path)
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE ticket_no = ?",
            ("7240005432906569",),
        ).fetchone()[0]
        == 1
    )
    conn.close()
