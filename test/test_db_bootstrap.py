"""Tests for database date synchronization."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from data.data_base import backup_file, local_file


@pytest.mark.integration
def test_update_dates_returns_local_file_path():
    from data.data_base.init_db import update_dates

    result = update_dates()
    assert result == local_file
    assert Path(result).exists()


@pytest.mark.integration
def test_update_dates_refreshes_flight_dates():
    from data.data_base.init_db import update_dates

    update_dates()
    conn = sqlite3.connect(local_file)
    df = pd.read_sql(
        "SELECT scheduled_departure FROM flights WHERE scheduled_departure != '\\N' LIMIT 5",
        conn,
    )
    conn.close()

    assert not df.empty
    dates = pd.to_datetime(df["scheduled_departure"], errors="coerce")
    assert dates.notna().all()


@pytest.mark.integration
def test_update_dates_creates_reservation_tables_without_booked_flag():
    from data.data_base.init_db import update_dates

    update_dates()
    conn = sqlite3.connect(local_file)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for name in ("hotel_reservations", "car_reservations", "activity_reservations"):
        assert name in tables
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        assert count == 0

    for catalog in ("hotels", "car_rentals", "trip_recommendations"):
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({catalog})").fetchall()]
        assert "booked" not in cols

    luis_tickets = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE passenger_id = ?",
        ("3442 587242",),
    ).fetchone()[0]
    conn.close()
    assert luis_tickets >= 1



def test_sync_database_dates_delegates_to_update_dates():
    from api_view.db_bootstrap import sync_database_dates

    with patch("api_view.db_bootstrap.update_dates", return_value="/tmp/db.sqlite") as mock_update:
        path = sync_database_dates()
    assert path == "/tmp/db.sqlite"
    mock_update.assert_called_once()
