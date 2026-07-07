"""Create the demo SQLite travel database used by MCP tools."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "mcp_server" / "travel_new.sqlite"
BACKUP_PATH = PROJECT_DIR / "mcp_server" / "travel2.sqlite"

# UTC+3 — matches flights_tools.py (Etc/GMT-3)
TZ = timezone(timedelta(hours=3))


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f") + "+0300"


def seed() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript(
        """
        DROP TABLE IF EXISTS boarding_passes;
        DROP TABLE IF EXISTS ticket_flights;
        DROP TABLE IF EXISTS tickets;
        DROP TABLE IF EXISTS flights;
        DROP TABLE IF EXISTS hotels;
        DROP TABLE IF EXISTS car_rentals;
        DROP TABLE IF EXISTS activity_recommendations;

        CREATE TABLE flights (
            flight_id INTEGER PRIMARY KEY,
            flight_no TEXT,
            departure_airport TEXT,
            arrival_airport TEXT,
            scheduled_departure TEXT,
            scheduled_arrival TEXT
        );

        CREATE TABLE tickets (
            ticket_no TEXT PRIMARY KEY,
            book_ref TEXT,
            passenger_id TEXT
        );

        CREATE TABLE ticket_flights (
            ticket_no TEXT,
            flight_id INTEGER,
            fare_conditions TEXT
        );

        CREATE TABLE boarding_passes (
            ticket_no TEXT,
            flight_id INTEGER,
            seat_no TEXT
        );

        CREATE TABLE hotels (
            id INTEGER PRIMARY KEY,
            name TEXT,
            location TEXT,
            booked INTEGER DEFAULT 0,
            checkin_date TEXT,
            checkout_date TEXT
        );

        CREATE TABLE car_rentals (
            id INTEGER PRIMARY KEY,
            name TEXT,
            location TEXT,
            booked INTEGER DEFAULT 0,
            start_date TEXT,
            end_date TEXT
        );

        CREATE TABLE activity_recommendations (
            id INTEGER PRIMARY KEY,
            name TEXT,
            location TEXT,
            keywords TEXT,
            booked INTEGER DEFAULT 0,
            details TEXT
        );
        """
    )

    now = datetime.now(TZ)
    dep1 = now + timedelta(days=7, hours=5)
    arr1 = dep1 + timedelta(hours=5, minutes=30)
    dep2 = now + timedelta(days=8, hours=9)
    arr2 = dep2 + timedelta(hours=6)
    dep3 = now + timedelta(days=14, hours=14)
    arr3 = dep3 + timedelta(hours=5, minutes=15)

    flights = [
        (1, "UA100", "SFO", "JFK", _ts(dep1), _ts(arr1)),
        (2, "AA200", "SFO", "JFK", _ts(dep2), _ts(arr2)),
        (3, "DL300", "JFK", "SFO", _ts(dep3), _ts(arr3)),
        (4, "UA150", "LAX", "ORD", _ts(now + timedelta(days=10)), _ts(now + timedelta(days=10, hours=4))),
    ]
    cur.executemany("INSERT INTO flights VALUES (?,?,?,?,?,?)", flights)

    passenger_id = "3442 587679"
    cur.execute(
        "INSERT INTO tickets VALUES (?, ?, ?)",
        ("1234567890123", "ABC123", passenger_id),
    )
    cur.execute(
        "INSERT INTO ticket_flights VALUES (?, ?, ?)",
        ("1234567890123", 1, "Economy"),
    )
    cur.execute(
        "INSERT INTO boarding_passes VALUES (?, ?, ?)",
        ("1234567890123", 1, "12A"),
    )

    hotels = [
        (1, "Grand Hyatt New York", "New York, NY", 0, None, None),
        (2, "Hilton San Francisco", "San Francisco, CA", 0, None, None),
        (3, "Marriott JFK Airport", "Jamaica, NY", 0, None, None),
    ]
    cur.executemany("INSERT INTO hotels VALUES (?,?,?,?,?,?)", hotels)

    cars = [
        (1, "Hertz", "San Francisco Airport", 0, None, None),
        (2, "Enterprise", "New York JFK", 0, None, None),
        (3, "Avis", "Los Angeles LAX", 0, None, None),
    ]
    cur.executemany("INSERT INTO car_rentals VALUES (?,?,?,?,?,?)", cars)

    activities = [
        (1, "Statue of Liberty Tour", "New York, NY", "sightseeing,landmark", 0, "Ferry + guided tour"),
        (2, "Golden Gate Bridge Walk", "San Francisco, CA", "outdoor,scenic", 0, "Self-guided walk"),
        (3, "Broadway Show", "New York, NY", "entertainment,theatre", 0, "Evening performance"),
    ]
    cur.executemany("INSERT INTO activity_recommendations VALUES (?,?,?,?,?,?)", activities)

    conn.commit()
    conn.close()

    import shutil

    shutil.copy2(DB_PATH, BACKUP_PATH)
    return DB_PATH


if __name__ == "__main__":
    path = seed()
    print(f"Demo database created: {path}")
