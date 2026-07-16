from sqlite3 import connect
from datetime import date, datetime
from fastmcp import FastMCP
from data.data_base import db

GROUP_NAME = "car"


def register_car_tools(mcp: FastMCP):
    """Register all the tools for car rental"""

    @mcp.tool(name=f"{GROUP_NAME}_search")
    def search_car_rentals(
        location: str | None = None,
        name: str | None = None,
    ) -> list[dict]:
        """
        Search car rental catalog by location and company name.

        Parameters:
        - location (Optional[str])
        - name (Optional[str])

        Returns:
        - list[dict]: car rental catalog rows
        """
        conn = connect(db)
        cursor = conn.cursor()
        query = "SELECT * FROM car_rentals WHERE 1=1"
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
    def fetch_user_car_reservations(user_id: str) -> list[dict]:
        """
        List car rental reservations for a user.

        Parameters:
        - user_id (str): conversation user id
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
                r.rental_id,
                r.start_date,
                r.end_date,
                r.status,
                c.name,
                c.location,
                c.price_tier
            FROM car_reservations r
            JOIN car_rentals c ON c.id = r.rental_id
            WHERE r.user_id = ? AND r.status = 'booked'
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        column_names = [column[0] for column in cursor.description]
        conn.close()
        return [dict(zip(column_names, row)) for row in rows]

    @mcp.tool(name=f"{GROUP_NAME}_book")
    def book_car_rental(
        user_id: str,
        rental_id: int,
        start_date: datetime | date | None = None,
        end_date: datetime | date | None = None,
    ) -> str:
        """
        Create a car rental reservation for a user.

        Parameters:
        - user_id (str)
        - rental_id (int): catalog id from car_search
        - start_date / end_date: optional rental period
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM car_rentals WHERE id = ?", (rental_id,))
        if not cursor.fetchone():
            conn.close()
            return f"Cannot find car rental {rental_id}"

        cursor.execute(
            """
            INSERT INTO car_reservations
                (user_id, rental_id, start_date, end_date, status)
            VALUES (?, ?, ?, ?, 'booked')
            """,
            (user_id, rental_id, start_date, end_date),
        )
        reservation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return (
            f"Car reservation created successfully. "
            f"reservation_id={reservation_id}, rental_id={rental_id}, user_id={user_id}."
        )

    @mcp.tool(name=f"{GROUP_NAME}_update")
    def update_car_rental(
        reservation_id: int,
        user_id: str,
        start_date: datetime | date | None = None,
        end_date: datetime | date | None = None,
    ) -> str:
        """
        Update dates on an existing car reservation.

        Parameters:
        - reservation_id (int): booking id
        - user_id (str)
        - start_date / end_date: optional new dates
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM car_reservations
            WHERE id = ? AND user_id = ? AND status = 'booked'
            """,
            (reservation_id, user_id),
        )
        if not cursor.fetchone():
            conn.close()
            return (
                f"Cannot find active car reservation {reservation_id} "
                f"for user {user_id}."
            )

        if start_date is not None:
            cursor.execute(
                "UPDATE car_reservations SET start_date = ? WHERE id = ?",
                (start_date, reservation_id),
            )
        if end_date is not None:
            cursor.execute(
                "UPDATE car_reservations SET end_date = ? WHERE id = ?",
                (end_date, reservation_id),
            )

        conn.commit()
        conn.close()
        return f"Car reservation {reservation_id} updated successfully."

    @mcp.tool(name=f"{GROUP_NAME}_cancel")
    def cancel_car_rental(reservation_id: int, user_id: str) -> str:
        """
        Cancel a car reservation owned by the user.

        Parameters:
        - reservation_id (int)
        - user_id (str)
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE car_reservations
            SET status = 'cancelled'
            WHERE id = ? AND user_id = ? AND status = 'booked'
            """,
            (reservation_id, user_id),
        )
        conn.commit()
        updated = cursor.rowcount
        conn.close()

        if updated > 0:
            return f"Car reservation {reservation_id} cancelled successfully."
        return (
            f"Cannot find active car reservation {reservation_id} "
            f"for user {user_id}."
        )
