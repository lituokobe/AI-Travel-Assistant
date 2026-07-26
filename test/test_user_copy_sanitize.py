"""Tests for user-facing copy sanitizer."""

from api_view.services.user_copy_sanitize import sanitize_user_facing_text


def test_strips_price_sensitivity_phrase():
    raw = (
        "Given your medium price sensitivity, Europcar (Economy) or Thrifty "
        "(Midsize) would be the most natural fits."
    )
    out = sanitize_user_facing_text(raw)
    assert "price sensitivity" not in out.lower()
    assert "Europcar" in out


def test_replaces_package_planning_process():
    raw = (
        "A 3-day trip would be 4–7 September. "
        "Let me follow the package planning process."
    )
    out = sanitize_user_facing_text(raw)
    assert "package planning process" not in out.lower()
    assert "get started" in out.lower()
