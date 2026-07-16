"""Integration tests for per-user reservation tables and flight passenger alias."""

from __future__ import annotations

import sqlite3

import pytest

from data.data_base import local_file


@pytest.mark.integration
def test_hotel_car_activity_reservation_roundtrip():
    from data.data_base.init_db import update_dates

    update_dates()
    user_id = "3442 587242"
    conn = sqlite3.connect(local_file)
    cur = conn.cursor()

    hotel_id = cur.execute("SELECT id FROM hotels LIMIT 1").fetchone()[0]
    rental_id = cur.execute("SELECT id FROM car_rentals LIMIT 1").fetchone()[0]
    activity_id = cur.execute("SELECT id FROM trip_recommendations LIMIT 1").fetchone()[0]

    cur.execute(
        """
        INSERT INTO hotel_reservations (user_id, hotel_id, checkin_date, checkout_date, status)
        VALUES (?, ?, '2026-08-01', '2026-08-05', 'booked')
        """,
        (user_id, hotel_id),
    )
    hotel_res_id = cur.lastrowid

    cur.execute(
        """
        INSERT INTO car_reservations (user_id, rental_id, start_date, end_date, status)
        VALUES (?, ?, '2026-08-01', '2026-08-05', 'booked')
        """,
        (user_id, rental_id),
    )
    car_res_id = cur.lastrowid

    cur.execute(
        """
        INSERT INTO activity_reservations (user_id, recommendation_id, details, status)
        VALUES (?, ?, 'demo notes', 'booked')
        """,
        (user_id, activity_id),
    )
    activity_res_id = cur.lastrowid
    conn.commit()

    assert (
        cur.execute(
            "SELECT COUNT(*) FROM hotel_reservations WHERE user_id=? AND status='booked'",
            (user_id,),
        ).fetchone()[0]
        == 1
    )
    assert (
        cur.execute(
            "SELECT COUNT(*) FROM car_reservations WHERE user_id=? AND status='booked'",
            (user_id,),
        ).fetchone()[0]
        == 1
    )
    assert (
        cur.execute(
            "SELECT COUNT(*) FROM activity_reservations WHERE user_id=? AND status='booked'",
            (user_id,),
        ).fetchone()[0]
        == 1
    )

    cur.execute(
        "UPDATE hotel_reservations SET status='cancelled' WHERE id=? AND user_id=?",
        (hotel_res_id, user_id),
    )
    cur.execute(
        "UPDATE car_reservations SET status='cancelled' WHERE id=? AND user_id=?",
        (car_res_id, user_id),
    )
    cur.execute(
        "UPDATE activity_reservations SET status='cancelled' WHERE id=? AND user_id=?",
        (activity_res_id, user_id),
    )
    conn.commit()
    conn.close()


@pytest.mark.integration
def test_luis_has_existing_flight_ticket():
    from data.data_base.init_db import update_dates

    update_dates()
    conn = sqlite3.connect(local_file)
    rows = conn.execute(
        """
        SELECT t.ticket_no, f.flight_no, f.departure_airport, f.arrival_airport
        FROM tickets t
        JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
        JOIN flights f ON f.flight_id = tf.flight_id
        WHERE t.passenger_id = ?
        """,
        ("3442 587242",),
    ).fetchall()
    conn.close()
    assert len(rows) >= 1
