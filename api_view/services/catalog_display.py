"""Resolve catalog / flight IDs to customer-facing labels (no internal IDs)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from data.data_base import db


def _query_one(sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
    try:
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(sql, params).fetchone()
        finally:
            conn.close()
        return row
    except Exception:
        return None


def hotel_display_name(hotel_id: Any) -> str | None:
    row = _query_one("SELECT name, location FROM hotels WHERE id = ?", (hotel_id,))
    if not row:
        return None
    name, location = row
    if location:
        return f"{name} ({location})"
    return str(name)


def car_display_name(rental_id: Any) -> str | None:
    row = _query_one(
        "SELECT name, location, price_tier FROM car_rentals WHERE id = ?",
        (rental_id,),
    )
    if not row:
        return None
    name, location, tier = row
    parts = [str(name)]
    if location:
        parts.append(f"({location})")
    if tier:
        parts.append(f"— {tier}")
    return " ".join(parts)


def activity_display_name(recommendation_id: Any) -> str | None:
    row = _query_one(
        "SELECT name, location FROM trip_recommendations WHERE id = ?",
        (recommendation_id,),
    )
    if not row:
        return None
    name, location = row
    if location:
        return f"{name} ({location})"
    return str(name)


def flight_display_label(flight_id: Any) -> str | None:
    row = _query_one(
        """
        SELECT flight_no, departure_airport, arrival_airport,
               substr(scheduled_departure, 1, 16)
        FROM flights WHERE flight_id = ?
        """,
        (flight_id,),
    )
    if not row:
        return None
    flight_no, dep, arr, dep_time = row
    label = f"{flight_no} ({dep} → {arr})"
    if dep_time:
        label += f", {dep_time}"
    return label


def format_guest_line(
    user_id: Any | None,
    *,
    guest_name: str | None = None,
    label: str = "Guest",
) -> str | None:
    """Customer-facing guest line: name + optional ID."""
    name = (guest_name or "").strip() or None
    uid = str(user_id).strip() if user_id not in (None, "") else None
    if name and uid:
        return f"- {label}: {name} (ID: {uid})"
    if name:
        return f"- {label}: {name}"
    if uid:
        return f"- {label} ID: {uid}"
    return None


def _action_dedupe_key(action: dict[str, Any]) -> str:
    """Stable key for identical book/cancel args (order-independent)."""
    name = str(action.get("name") or "")
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    # Normalize for JSON: sort keys; stringify values
    normalized = {str(k): args[k] for k in sorted(args.keys())}
    try:
        payload = json.dumps(normalized, sort_keys=True, default=str)
    except TypeError:
        payload = str(normalized)
    return f"{name}|{payload}"


def collapse_approval_actions(
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Collapse duplicate approval actions for display.

    Party-size demos often emit N identical ``flights_book`` calls for the same
    passenger. The UI should show one line with a quantity, while resume still
    approves every hanging tool call.
    """
    groups: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}
    for action in actions:
        if not isinstance(action, dict):
            continue
        key = _action_dedupe_key(action)
        if key in index_by_key:
            groups[index_by_key[key]]["quantity"] += 1
            continue
        index_by_key[key] = len(groups)
        groups.append(
            {
                "name": action.get("name") or "action",
                "args": action.get("args") or {},
                "quantity": 1,
            }
        )
    return groups


def quantity_label(tool_name: str, quantity: int) -> str | None:
    """Customer-facing quantity line when the same service is booked multiple times."""
    if quantity <= 1:
        return None
    key = (tool_name or "").strip()
    if key.startswith("flights_"):
        return f"- Seats / quantity: {quantity}"
    if key.startswith("hotels_"):
        return f"- Rooms / quantity: {quantity}"
    if key.startswith("car_"):
        return f"- Vehicles / quantity: {quantity}"
    if key.startswith("activity_"):
        return f"- Tickets / quantity: {quantity}"
    return f"- Quantity: {quantity}"


def format_approval_arg_lines(
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    guest_name: str | None = None,
) -> list[str]:
    """
    Render HITL args in customer-service language.

    Hides internal catalog IDs (hotel_id, rental_id, recommendation_id, flight_id)
    in favor of public names / flight numbers. Booking identifiers (ticket_no,
    reservation_id, book_ref) and passenger/guest IDs remain visible.
    """
    if not isinstance(args, dict) or not args:
        return []

    lines: list[str] = []
    shown: set[str] = set()

    def add(line: str | None) -> None:
        if line:
            lines.append(line)

    # Catalog / flight lookups first (never print raw internal IDs)
    if "hotel_id" in args and args["hotel_id"] not in (None, ""):
        shown.add("hotel_id")
        name = hotel_display_name(args["hotel_id"])
        add(f"- Hotel: {name}" if name else "- Hotel: (selected property)")

    if "rental_id" in args and args["rental_id"] not in (None, ""):
        shown.add("rental_id")
        name = car_display_name(args["rental_id"])
        add(f"- Car rental: {name}" if name else "- Car rental: (selected option)")

    if "recommendation_id" in args and args["recommendation_id"] not in (None, ""):
        shown.add("recommendation_id")
        name = activity_display_name(args["recommendation_id"])
        add(f"- Activity: {name}" if name else "- Activity: (selected option)")
        # Prefer residual notes after the activity title when details repeats the name
        details = args.get("details")
        if name and isinstance(details, str) and details.strip():
            residual = details.strip()
            # Strip leading activity name variants
            short_name = name.split(" (")[0].strip()
            for prefix in (name, short_name):
                if residual.lower().startswith(prefix.lower()):
                    residual = residual[len(prefix) :].lstrip(" —-:|")
                    break
            if residual and residual != details.strip():
                args = {**args, "details": residual}
            elif residual.lower() == short_name.lower() or not residual:
                args = {**args, "details": None}
    if "flight_id" in args and args["flight_id"] not in (None, ""):
        shown.add("flight_id")
        label = flight_display_label(args["flight_id"])
        add(f"- Flight: {label}" if label else "- Flight: (selected flight)")

    if "new_flight_id" in args and args["new_flight_id"] not in (None, ""):
        shown.add("new_flight_id")
        label = flight_display_label(args["new_flight_id"])
        add(f"- New flight: {label}" if label else "- New flight: (selected flight)")

    # Public / booking fields
    public_order = [
        ("ticket_no", "Ticket number"),
        ("book_ref", "Booking reference"),
        ("reservation_id", "Reservation ID"),
        ("checkin_date", "Check-in"),
        ("checkout_date", "Check-out"),
        ("start_date", "Start date"),
        ("end_date", "End date"),
        ("fare_conditions", "Cabin / fare"),
        ("details", "Details"),
    ]
    for key, label in public_order:
        if key not in args or key in shown or args[key] in (None, ""):
            continue
        shown.add(key)
        value = args[key]
        if key == "details" and isinstance(value, str):
            # Prefer short details; activity name already shown above
            text = " ".join(value.split())
            if len(text) > 160:
                text = text[:157] + "…"
            add(f"- {label}: {text}")
        else:
            add(f"- {label}: {value}")

    # Guest / passenger (with display name when known)
    guest_keys = ("user_id", "passenger_id")
    guest_shown = False
    for key in guest_keys:
        if key not in args or args[key] in (None, ""):
            continue
        shown.add(key)
        if not guest_shown:
            guest_label = "Passenger" if key == "passenger_id" else "Guest"
            add(format_guest_line(args[key], guest_name=guest_name, label=guest_label))
            guest_shown = True

    # Any remaining non-internal fields
    hidden = {
        "tool",
        "name",
        "type",
        "hotel_id",
        "rental_id",
        "recommendation_id",
        "flight_id",
        "new_flight_id",
        "user_id",
        "passenger_id",
    }
    for key, value in args.items():
        if key in shown or key in hidden or value in (None, ""):
            continue
        if key.endswith("_id") and key not in (
            "reservation_id",
            "ticket_no",
        ):
            # Skip unknown internal-looking ids
            continue
        add(f"- {key.replace('_', ' ').title()}: {value}")

    return lines
