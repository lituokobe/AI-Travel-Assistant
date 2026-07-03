from sqlite3 import connect
from fastmcp import FastMCP
from mcp_server.tools import db

GROUP_NAME = "activity"

def register_activity_tools(mcp: FastMCP):
    """Register all the tools for activity management"""

    @mcp.tool(name=f"{GROUP_NAME}_search")
    def search_activity_recommendations(
            location: str|None = None,
            name: str|None = None,
            keywords: str|None = None,
    ) -> list[dict]:
        """
        Search activities on location, name and keywords.

        Parameters:
        - location (Optional[str]): location of the activity, default is None
        - name (Optional[str]): name of the activity, default is None
        - keywords: keywords relevant to the activity, default is None

        Returns:
        - list[dict]: list of dictionaries with activities that satisfy the requirement
        """
        conn = connect(db)
        cursor = conn.cursor()
        query = "SELECT * FROM activity_recommendations WHERE 1=1"
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

        conn.close()

        return [
            dict(zip([column[0] for column in cursor.description], row)) for row in results
        ]


    @mcp.tool(name=f"{GROUP_NAME}_book")
    def book_activity(recommendation_id: int) -> str:
        """
        Book an activity based on recommendation id.

        Parameters:
        - recommendation_id (int): recommendation id of the activity to book

        Returns:
        - str: a string to indicate if the activity is successfully booked
        """
        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE activity_recommendations SET booked = 1 WHERE id = ?", (recommendation_id,)
        )
        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return f"Recommended activity  {recommendation_id} is booked successfully"
        else:
            conn.close()
            return f"Cannot find recommended activity {recommendation_id}"


    @mcp.tool(name=f"{GROUP_NAME}_update")
    def update_activity(recommendation_id: int, details: str) -> str:
        """
        Update activity details based on recommendation ID.

        Parameters:
        - hotel_id (int): id of the recommended activity to update
        - details (str): detailed information of the recommended activity

        Returns:
        - str: a string to indicate if the activity recommendation is updated successfully.
        """
        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE activity_recommendations SET details = ? WHERE id = ?",
            (details, recommendation_id),
        )
        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return f"activity recommendation {recommendation_id} is successfully updated"
        else:
            conn.close()
            return f"Cannot find activity recommendation {recommendation_id}"


    @mcp.tool(name=f"{GROUP_NAME}_cancel")
    def cancel_activity(recommendation_id: int) -> str:
        """
        Cancel activity recommendation based on ID.

        Parameters:
        - recommendation_id (int):id of the recommended activity

        Returns:
        - str: a string to indicate if the recommended activity is canceled successfully.
        """
        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE activity_recommendations SET booked = 0 WHERE id = ?", (recommendation_id,)
        )
        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return f"Recommended activity  {recommendation_id} is cancelled successfully"
        else:
            conn.close()
            return f"Cannot find activity recommendation {recommendation_id}"
