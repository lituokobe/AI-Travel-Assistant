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
    df = pd.read_sql("SELECT scheduled_departure FROM flights WHERE scheduled_departure != '\\N' LIMIT 5", conn)
    conn.close()

    assert not df.empty
    dates = pd.to_datetime(df["scheduled_departure"], errors="coerce")
    assert dates.notna().all()


def test_sync_database_dates_delegates_to_update_dates():
    from api_view.db_bootstrap import sync_database_dates

    with patch("api_view.db_bootstrap.update_dates", return_value="/tmp/db.sqlite") as mock_update:
        path = sync_database_dates()
    assert path == "/tmp/db.sqlite"
    mock_update.assert_called_once()
