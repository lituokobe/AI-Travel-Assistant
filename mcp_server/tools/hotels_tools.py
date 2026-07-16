from sqlite3 import connect
from datetime import date, datetime
from fastmcp import FastMCP
from data.data_base import db

GROUP_NAME = "hotels"


def register_hotels_tools(mcp: FastMCP):
    """Register all the tools for hotel booking"""

    @mcp.tool(name=f"{GROUP_NAME}_search")
    def search_hotels(
        location: str | None = None,
        name: str | None = None,
    ) -> list[dict]:
        """
        Search hotel catalog by location and name.

        Parameters:
        - location (Optional[str])
        - name (Optional[str])

        Returns:
        - list[dict]: hotels that satisfy the requirement
        """
        conn = connect(db)
        cursor = conn.cursor()
        query = "SELECT * FROM hotels WHERE 1=1"
        params = []

        if location:
            query += " AND location LIKE ?"
            params.append(f"%{location}%")
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")

        cursor.execute(query, params)
        results = cursor.fetchall()
        column_names = [column[0] for column in cursor.description]
        conn.close()

        return [dict(zip(column_names, row)) for row in results]

    @mcp.tool(name=f"{GROUP_NAME}_fetch")
    def fetch_user_hotel_reservations(user_id: str) -> list[dict]:
        """
        List hotel reservations for a user (source of truth: hotel_reservations).

        Parameters:
        - user_id (str): conversation user id

        Returns:
        - list[dict]: reservation rows joined with hotel catalog fields
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                r.id AS reservation_id,
                r.user_id,
                r.hotel_id,
                r.checkin_date,
                r.checkout_date,
                r.status,
                h.name,
                h.location,
                h.price_tier
            FROM hotel_reservations r
            JOIN hotels h ON h.id = r.hotel_id
            WHERE r.user_id = ? AND r.status = 'booked'
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        column_names = [column[0] for column in cursor.description]
        conn.close()
        return [dict(zip(column_names, row)) for row in rows]

    @mcp.tool(name=f"{GROUP_NAME}_book")
    def book_hotel(
        user_id: str,
        hotel_id: int,
        checkin_date: datetime | date | None = None,
        checkout_date: datetime | date | None = None,
    ) -> str:
        """
        Create a hotel reservation for a user.

        Parameters:
        - user_id (str): conversation user id
        - hotel_id (int): catalog hotel id from hotels_search
        - checkin_date / checkout_date: optional stay dates

        Returns:
        - str: confirmation including reservation (booking) id
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM hotels WHERE id = ?", (hotel_id,))
        if not cursor.fetchone():
            conn.close()
            return f"Cannot find hotel with ID {hotel_id}."

        cursor.execute(
            """
            INSERT INTO hotel_reservations
                (user_id, hotel_id, checkin_date, checkout_date, status)
            VALUES (?, ?, ?, ?, 'booked')
            """,
            (user_id, hotel_id, checkin_date, checkout_date),
        )
        reservation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return (
            f"Hotel reservation created successfully. "
            f"reservation_id={reservation_id}, hotel_id={hotel_id}, user_id={user_id}."
        )

    @mcp.tool(name=f"{GROUP_NAME}_update")
    def update_hotel(
        reservation_id: int,
        user_id: str,
        checkin_date: datetime | date | None = None,
        checkout_date: datetime | date | None = None,
    ) -> str:
        """
        Update dates on an existing hotel reservation.

        Parameters:
        - reservation_id (int): booking id from hotels_book / hotels_fetch
        - user_id (str): must own the reservation
        - checkin_date / checkout_date: optional new dates
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM hotel_reservations
            WHERE id = ? AND user_id = ? AND status = 'booked'
            """,
            (reservation_id, user_id),
        )
        if not cursor.fetchone():
            conn.close()
            return (
                f"Cannot find active hotel reservation {reservation_id} "
                f"for user {user_id}."
            )

        if checkin_date is not None:
            cursor.execute(
                "UPDATE hotel_reservations SET checkin_date = ? WHERE id = ?",
                (checkin_date, reservation_id),
            )
        if checkout_date is not None:
            cursor.execute(
                "UPDATE hotel_reservations SET checkout_date = ? WHERE id = ?",
                (checkout_date, reservation_id),
            )

        conn.commit()
        conn.close()
        return f"Hotel reservation {reservation_id} updated successfully."

    @mcp.tool(name=f"{GROUP_NAME}_cancel")
    def cancel_hotel(reservation_id: int, user_id: str) -> str:
        """
        Cancel a hotel reservation owned by the user.

        Parameters:
        - reservation_id (int): booking id
        - user_id (str): must own the reservation
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE hotel_reservations
            SET status = 'cancelled'
            WHERE id = ? AND user_id = ? AND status = 'booked'
            """,
            (reservation_id, user_id),
        )
        conn.commit()
        updated = cursor.rowcount
        conn.close()

        if updated > 0:
            return f"Hotel reservation {reservation_id} cancelled successfully."
        return (
            f"Cannot find active hotel reservation {reservation_id} "
            f"for user {user_id}."
        )
