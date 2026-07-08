"""Synchronize travel SQLite dates before agent or MCP startup."""

from __future__ import annotations

import logging

from data.data_base.init_db import update_dates

logger = logging.getLogger(__name__)


def sync_database_dates() -> str:
    """
    Reset the working DB from backup and shift dates to the current time.

    Delegates to ``data.data_base.init_db.update_dates`` so booking and flight
    timestamps stay realistic whenever the service starts.
    """
    path = update_dates()
    logger.info("Travel database dates synchronized: %s", path)
    return path
