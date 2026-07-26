"""Tests for customer-facing catalog label helpers."""

from api_view.services.catalog_display import (
    activity_display_name,
    format_approval_arg_lines,
    hotel_display_name,
)


def test_hotel_display_name_resolves():
    name = hotel_display_name(7)
    assert name is not None
    assert "Sheraton" in name
    assert "7" not in name


def test_activity_display_name_resolves():
    name = activity_display_name(3)
    assert name is not None
    assert "Zurich" in name or "Old Town" in name
    assert name.strip("3") == name  # no bare id


def test_format_hotels_book_hides_hotel_id_shows_guest_name():
    lines = format_approval_arg_lines(
        "hotels_book",
        {
            "user_id": "3442 587242",
            "hotel_id": 7,
            "checkin_date": "2026-07-30",
            "checkout_date": "2026-08-04",
        },
        guest_name="Luis",
    )
    text = "\n".join(lines)
    assert "hotel_id" not in text.lower()
    assert ": 7" not in text
    assert "Sheraton" in text
    assert "Luis" in text
    assert "3442 587242" in text
    assert "Check-in: 2026-07-30" in text


def test_format_activity_book_hides_recommendation_id():
    lines = format_approval_arg_lines(
        "activity_book",
        {
            "user_id": "3442 587242",
            "recommendation_id": 3,
            "details": "Zurich Old Town walking tour — Package C family trip",
        },
        guest_name="Luis",
    )
    text = "\n".join(lines)
    assert "recommendation_id" not in text.lower()
    assert "Activity:" in text
    assert ": 3\n" not in text + "\n"
    assert "Luis" in text
    # Residual notes without repeating the full title clutter
    assert "Package C" in text or "Details:" in text


def test_collapse_approval_actions_merges_duplicates():
    from api_view.services.catalog_display import collapse_approval_actions, quantity_label

    actions = [
        {
            "name": "flights_book",
            "args": {
                "passenger_id": "3442 587242",
                "flight_id": 19230,
                "fare_conditions": "Economy",
            },
        },
        {
            "name": "flights_book",
            "args": {
                "flight_id": 19230,
                "fare_conditions": "Economy",
                "passenger_id": "3442 587242",
            },
        },
        {
            "name": "flights_book",
            "args": {
                "passenger_id": "3442 587242",
                "flight_id": 1420,
                "fare_conditions": "Economy",
            },
        },
        {
            "name": "flights_book",
            "args": {
                "passenger_id": "3442 587242",
                "flight_id": 1420,
                "fare_conditions": "Economy",
            },
        },
    ]
    grouped = collapse_approval_actions(actions)
    assert len(grouped) == 2
    assert grouped[0]["quantity"] == 2
    assert grouped[1]["quantity"] == 2
    assert quantity_label("flights_book", 2) == "- Seats / quantity: 2"
    assert quantity_label("flights_book", 1) is None
