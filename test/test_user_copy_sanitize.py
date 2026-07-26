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


def test_replaces_change_of_plans_workflow():
    raw = "Let me follow the change-of-plans workflow."
    out = sanitize_user_facing_text(raw)
    assert "change-of-plans workflow" not in out.lower()
    assert "get started" in out.lower()


def test_replaces_package_planning_process():
    raw = (
        "A 3-day trip would be 4–7 September. "
        "Let me follow the package planning process."
    )
    out = sanitize_user_facing_text(raw)
    assert "package planning process" not in out.lower()
    assert "get started" in out.lower()


def test_strips_skill_and_progress_filler():
    raw = (
        "Let me get started on planning this Zurich trip. "
        "I'll first check the package skill and your available options. "
        "I have what I need. Let me set up the plan and start researching flights. "
        "Good, I have the flight skills loaded. "
        "Good progress — flights found. "
        "Here are your options for Zurich."
    )
    out = sanitize_user_facing_text(raw)
    assert "skill" not in out.lower()
    assert "good progress" not in out.lower()
    assert "i have what i need" not in out.lower()
    assert "Here are your options for Zurich." in out
