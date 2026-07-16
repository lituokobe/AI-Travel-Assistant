from sqlite3 import connect
from datetime import date, datetime
import secrets
import pytz
from fastmcp import FastMCP
from data.data_base import db

GROUP_NAME = "flights"


def register_flights_tools(mcp: FastMCP):
    """Register all the tools for flights management"""

    @mcp.tool(name=f"{GROUP_NAME}_fetch")
    def fetch_user_flight_information(passenger_id: str) -> list[dict]:
        """
        Get a passenger's flight and seat information based on their ID.

        Parameters:
        - passenger_id (str): airline passenger id (same value as the conversation user_id)

        Return:
        - list of each ticket's details, flight and seat information, in a dictionary
        """
        if not passenger_id:
            raise ValueError("Passenger ID is required")

        conn = connect(db)
        cursor = conn.cursor()

        query = """
        SELECT 
            t.ticket_no, t.book_ref,
            f.flight_id, f.flight_no, f.departure_airport, f.arrival_airport,
            f.scheduled_departure, f.scheduled_arrival,
            bp.seat_no, tf.fare_conditions
        FROM 
            tickets t
            JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
            JOIN flights f ON tf.flight_id = f.flight_id
            LEFT JOIN boarding_passes bp
                ON bp.ticket_no = t.ticket_no AND bp.flight_id = f.flight_id
        WHERE 
            t.passenger_id = ?
        """
        cursor.execute(query, (passenger_id,))
        rows = cursor.fetchall()
        column_names = [column[0] for column in cursor.description]
        results = [dict(zip(column_names, row)) for row in rows]

        cursor.close()
        conn.close()

        return results

    @mcp.tool(name=f"{GROUP_NAME}_search")
    def search_flights(
        departure_airport: str | None = None,
        arrival_airport: str | None = None,
        start_time: date | datetime | None = None,
        end_time: date | datetime | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Search flights based on parameters and limits of returns.

        Parameters:
        - departure_airport (Optional[str])
        - arrival_airport (Optional[str])
        - start_time (Optional[date | datetime])
        - end_time (Optional[date | datetime])
        - limit (int): maximum returns, by default 20

        Returns:
        - list of flights
        """
        conn = connect(db)
        cursor = conn.cursor()

        query = "SELECT * FROM flights WHERE 1 = 1"
        params = []

        if departure_airport:
            query += " AND departure_airport = ?"
            params.append(departure_airport)

        if arrival_airport:
            query += " AND arrival_airport = ?"
            params.append(arrival_airport)

        if start_time:
            query += " AND scheduled_departure >= ?"
            params.append(start_time)

        if end_time:
            query += " AND scheduled_departure <= ?"
            params.append(end_time)

        query += " LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        column_names = [column[0] for column in cursor.description]
        results = [dict(zip(column_names, row)) for row in rows]

        cursor.close()
        conn.close()

        return results

    @mcp.tool(name=f"{GROUP_NAME}_book")
    def book_flight(
        passenger_id: str,
        flight_id: int,
        fare_conditions: str = "Economy",
    ) -> str:
        """
        Create a new flight ticket for a passenger on a given flight.

        This is distinct from flights_update, which rebooks an existing ticket.

        Parameters:
        - passenger_id (str): airline passenger id (same as conversation user_id)
        - flight_id (int): target flight from flights_search
        - fare_conditions (str): fare class, default Economy

        Returns:
        - str: booking confirmation including ticket_no and book_ref
        """
        if not passenger_id:
            raise ValueError("Passenger ID is required")

        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT flight_id, scheduled_departure FROM flights WHERE flight_id = ?",
            (flight_id,),
        )
        flight = cursor.fetchone()
        if not flight:
            cursor.close()
            conn.close()
            return f"Cannot find flight with ID {flight_id}."

        timezone = pytz.timezone("Etc/GMT-3")
        current_time = datetime.now(tz=timezone)
        departure_raw = flight[1]
        if isinstance(departure_raw, str):
            departure_time = datetime.strptime(
                departure_raw, "%Y-%m-%d %H:%M:%S.%f%z"
            )
        else:
            departure_time = departure_raw
            if departure_time.tzinfo is None:
                departure_time = timezone.localize(departure_time)

        time_until = (departure_time - current_time).total_seconds()
        if time_until < (3 * 3600):
            cursor.close()
            conn.close()
            return (
                f"Not allowed to book a flight departing in less than 3 hours. "
                f"The departure time is {departure_time}."
            )

        ticket_no = f"{secrets.randbelow(10**16):016d}"
        book_ref = secrets.token_hex(3).upper()

        cursor.execute(
            "INSERT INTO bookings (book_ref, book_date, total_amount) VALUES (?, ?, ?)",
            (book_ref, datetime.now(tz=timezone).isoformat(), 0),
        )
        cursor.execute(
            "INSERT INTO tickets (ticket_no, book_ref, passenger_id) VALUES (?, ?, ?)",
            (ticket_no, book_ref, passenger_id),
        )
        cursor.execute(
            """
            INSERT INTO ticket_flights (ticket_no, flight_id, fare_conditions, amount)
            VALUES (?, ?, ?, ?)
            """,
            (ticket_no, flight_id, fare_conditions, 0),
        )
        conn.commit()
        cursor.close()
        conn.close()

        return (
            f"Flight booked successfully. ticket_no={ticket_no}, "
            f"book_ref={book_ref}, flight_id={flight_id}, "
            f"passenger_id={passenger_id}, fare_conditions={fare_conditions}."
        )

    @mcp.tool(name=f"{GROUP_NAME}_update")
    def update_ticket_to_new_flight(
        ticket_no: str,
        new_flight_id: int,
        passenger_id: str,
    ) -> str:
        """
        Rebook an existing ticket to a different flight.

        Parameters:
        - ticket_no (str)
        - new_flight_id (int)
        - passenger_id (str): airline passenger id (same as conversation user_id)

        Returns:
        - str: Message from operation results
        """
        if not passenger_id:
            raise ValueError("Passenger ID is required")

        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT departure_airport, arrival_airport, scheduled_departure FROM flights WHERE flight_id = ?",
            (new_flight_id,),
        )
        new_flight = cursor.fetchone()
        if not new_flight:
            cursor.close()
            conn.close()
            return "New flight ID is invalid."
        column_names = [column[0] for column in cursor.description]
        new_flight_dict = dict(zip(column_names, new_flight))

        timezone = pytz.timezone("Etc/GMT-3")
        current_time = datetime.now(tz=timezone)
        departure_raw = new_flight_dict["scheduled_departure"]
        if isinstance(departure_raw, str):
            try:
                departure_time = datetime.strptime(
                    departure_raw, "%Y-%m-%d %H:%M:%S.%f%z"
                )
            except ValueError:
                departure_time = datetime.fromisoformat(departure_raw)
        else:
            departure_time = departure_raw
            if getattr(departure_time, "tzinfo", None) is None:
                departure_time = timezone.localize(departure_time)
        time_until = (departure_time - current_time).total_seconds()
        if time_until < (3 * 3600):
            cursor.close()
            conn.close()
            return (
                f"Not allowed to arrange a flight departing in less than 3 hours. "
                f"The departure time is {departure_time}."
            )

        cursor.execute(
            "SELECT flight_id FROM ticket_flights WHERE ticket_no = ?", (ticket_no,)
        )
        current_flight = cursor.fetchone()
        if not current_flight:
            cursor.close()
            conn.close()
            return "Cannot find ticket with the given ticket no."

        cursor.execute(
            "SELECT * FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
            (ticket_no, passenger_id),
        )
        current_ticket = cursor.fetchone()
        if not current_ticket:
            cursor.close()
            conn.close()
            return (
                f"Current passenger id is {passenger_id}, "
                f"not the owner of {ticket_no}."
            )

        cursor.execute(
            "UPDATE ticket_flights SET flight_id = ? WHERE ticket_no = ?",
            (new_flight_id, ticket_no),
        )
        conn.commit()

        cursor.close()
        conn.close()
        return "The ticket is updated with the new flight."

    @mcp.tool(name=f"{GROUP_NAME}_cancel")
    def cancel_ticket(ticket_no: str, passenger_id: str) -> str:
        """
        Cancel passenger ticket and delete flight segments from the database.

        Parameters:
        - ticket_no (str)
        - passenger_id (str): airline passenger id (same as conversation user_id)

        Return:
        - str: message from operation results
        """
        if not passenger_id:
            raise ValueError("passenger ID is required")

        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT flight_id FROM ticket_flights WHERE ticket_no = ?", (ticket_no,)
        )
        existing_ticket = cursor.fetchone()
        if not existing_ticket:
            cursor.close()
            conn.close()
            return "Cannot find ticket with the given ticket no."

        cursor.execute(
            "SELECT flight_id FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
            (ticket_no, passenger_id),
        )
        current_ticket = cursor.fetchone()
        if not current_ticket:
            cursor.close()
            conn.close()
            return (
                f"Current passenger id is {passenger_id}, "
                f"not the owner of {ticket_no}."
            )

        cursor.execute("DELETE FROM ticket_flights WHERE ticket_no = ?", (ticket_no,))
        conn.commit()

        cursor.close()
        conn.close()
        return "The ticket has been cancelled successfully."
