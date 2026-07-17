"""Tests for store-safe user id sanitization."""

from agent.config import ANONYMOUS_USER_ID, sanitize_store_user_id


def test_sanitize_passenger_id_with_space():
    assert sanitize_store_user_id("3442 587242") == "3442_587242"


def test_sanitize_preserves_safe_ids():
    assert sanitize_store_user_id("user-001") == "user-001"
    assert sanitize_store_user_id("alice@example.com") == "alice@example.com"


def test_sanitize_empty_falls_back():
    assert sanitize_store_user_id("") == ANONYMOUS_USER_ID
    assert sanitize_store_user_id(None) == ANONYMOUS_USER_ID
