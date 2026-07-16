from sqlite3 import connect
from fastmcp import FastMCP
from data.data_base import db

GROUP_NAME = "activity"
CATALOG_TABLE = "trip_recommendations"


def register_activity_tools(mcp: FastMCP):
    """Register all the tools for activity management"""

    @mcp.tool(name=f"{GROUP_NAME}_search")
    def search_activity_recommendations(
        location: str | None = None,
        name: str | None = None,
        keywords: str | None = None,
    ) -> list[dict]:
        """
        Search activity catalog by location, name and keywords.

        Parameters:
        - location (Optional[str])
        - name (Optional[str])
        - keywords: comma-separated keywords

        Returns:
        - list[dict]: matching trip_recommendations rows
        """
        conn = connect(db)
        cursor = conn.cursor()
        query = f"SELECT * FROM {CATALOG_TABLE} WHERE 1=1"
        params = []

        if location:
            query += " AND location LIKE ?"
            params.append(f"%{location}%")
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        if keywords:
            keyword_list = keywords.split(",")
            keyword_conditions = " OR ".join(["keywords LIKE ?" for _ in keyword_list])
            query += f" AND ({keyword_conditions})"
            params.extend([f"%{keyword.strip()}%" for keyword in keyword_list])

        cursor.execute(query, params)
        results = cursor.fetchall()
        column_names = [column[0] for column in cursor.description]
        conn.close()

        return [dict(zip(column_names, row)) for row in results]

    @mcp.tool(name=f"{GROUP_NAME}_fetch")
    def fetch_user_activity_reservations(user_id: str) -> list[dict]:
        """
        List activity reservations for a user.

        Parameters:
        - user_id (str): conversation user id
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                r.id AS reservation_id,
                r.user_id,
                r.recommendation_id,
                r.details AS reservation_details,
                r.status,
                t.name,
                t.location,
                t.keywords,
                t.details AS catalog_details
            FROM activity_reservations r
            JOIN {CATALOG_TABLE} t ON t.id = r.recommendation_id
            WHERE r.user_id = ? AND r.status = 'booked'
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        column_names = [column[0] for column in cursor.description]
        conn.close()
        return [dict(zip(column_names, row)) for row in rows]

    @mcp.tool(name=f"{GROUP_NAME}_book")
    def book_activity(
        user_id: str,
        recommendation_id: int,
        details: str | None = None,
    ) -> str:
        """
        Create an activity reservation for a user.

        Parameters:
        - user_id (str)
        - recommendation_id (int): catalog id from activity_search
        - details (Optional[str]): optional notes on the reservation
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id FROM {CATALOG_TABLE} WHERE id = ?", (recommendation_id,)
        )
        if not cursor.fetchone():
            conn.close()
            return f"Cannot find recommended activity {recommendation_id}"

        cursor.execute(
            """
            INSERT INTO activity_reservations
                (user_id, recommendation_id, details, status)
            VALUES (?, ?, ?, 'booked')
            """,
            (user_id, recommendation_id, details),
        )
        reservation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return (
            f"Activity reservation created successfully. "
            f"reservation_id={reservation_id}, recommendation_id={recommendation_id}, "
            f"user_id={user_id}."
        )

    @mcp.tool(name=f"{GROUP_NAME}_update")
    def update_activity(
        reservation_id: int,
        user_id: str,
        details: str,
    ) -> str:
        """
        Update details on an existing activity reservation.

        Parameters:
        - reservation_id (int): booking id
        - user_id (str)
        - details (str): new notes
        """
        if not user_id:
            raise ValueError("user_id is required")

        conn = connect(db)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE activity_reservations
            SET details = ?
            WHERE id = ? AND user_id = ? AND status = 'booked'
            """,
            (details, reservation_id, user_id),
        )
        conn.commit()
        updated = cursor.rowcount
        conn.close()

        if updated > 0:
            return f"Activity reservation {reservation_id} updated successfully."
        return (
            f"Cannot find active activity reservation {reservation_id} "
            f"for user {user_id}."
        )

    @mcp.tool(name=f"{GROUP_NAME}_cancel")
    def cancel_activity(reservation_id: int, user_id: str) -> str:
        """
        Cancel an activity reservation owned by the user.

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
            UPDATE activity_reservations
            SET status = 'cancelled'
            WHERE id = ? AND user_id = ? AND status = 'booked'
            """,
            (reservation_id, user_id),
        )
        conn.commit()
        updated = cursor.rowcount
        conn.close()

        if updated > 0:
            return f"Activity reservation {reservation_id} cancelled successfully."
        return (
            f"Cannot find active activity reservation {reservation_id} "
            f"for user {user_id}."
        )
