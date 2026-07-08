"""Tests for demo health utilities."""

from unittest.mock import patch

from demo.health import check_api, check_database, check_mcp, run_all_checks


def test_check_database_with_existing_backup():
    ok, msg = check_database()
    assert ok is True
    assert "SQLite OK" in msg


def test_check_mcp_not_running_by_default():
    ok, _ = check_mcp(host="127.0.0.1", port=59999)
    assert ok is False


def test_check_api_not_running_by_default():
    ok, _ = check_api(host="127.0.0.1", port=59998)
    assert ok is False


def test_run_all_checks_structure():
    with (
        patch("demo.health.check_redis", return_value=(True, "Redis OK")),
        patch("demo.health.check_mongodb", return_value=(True, "MongoDB OK")),
        patch("demo.health.check_mcp", return_value=(False, "down")),
        patch("demo.health.check_api", return_value=(False, "down")),
        patch("demo.health.check_database", return_value=(True, "db ok")),
    ):
        results = run_all_checks()
    assert len(results) == 5
    names = {r[0] for r in results}
    assert names == {"database", "redis", "mongodb", "mcp", "api"}
