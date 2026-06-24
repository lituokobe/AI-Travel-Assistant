from sqlite3 import connect
from datetime import date, datetime
from fastmcp import FastMCP
from mcp_server.tools import db

GROUP_NAME = "hotels"

def register_hotels_tools(mcp: FastMCP):
    """Register all the tools for hotel booking"""

    @mcp.tool(name=f"{GROUP_NAME}_search")
    def search_hotels(
            location: str|None = None,
            name: str|None = None
    ) -> list[dict]:
        """
        Search hotel based on location and name

        Parameters:
        - location (Optional[str])
        - name (Optional[str])

        Returns:
        - list[dict]: list of dictionaries with hotels that satisfy the requirement
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

        print('SQL to search hotel: ' + query, 'Parameters: ', params)
        cursor.execute(query, params)
        results = cursor.fetchall()
        print('Result of hotel searching: ', results)
        conn.close()

        return [
            dict(zip([column[0] for column in cursor.description], row)) for row in results
        ]


    @mcp.tool(name=f"{GROUP_NAME}_book")
    def book_hotel(hotel_id: int) -> str:
        """
        Book hotel based on hotel id.

        Parameters:
        - hotel_id (int)

        Returns:
        - str: a string to indicate if the hotel is successfully booked
        """
        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute("UPDATE hotels SET booked = 1 WHERE id = ?", (hotel_id,))
        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return f"Hotel {hotel_id} is booked successfully."
        else:
            conn.close()
            return f"Cannot find hotel with ID {hotel_id}."


    @mcp.tool(name=f"{GROUP_NAME}_update")
    def update_hotel(
            hotel_id: int,
            checkin_date: datetime|date|None = None,
            checkout_date: datetime|date|None = None,
    ) -> str:
        """
        Update hotel checkin and checkout dates based on hotel ID.

        Parameters:
        - hotel_id (int)
        - checkin_date (Optional[Union[datetime, date]])
        - checkout_date (Optional[Union[datetime, date]])

        Returns:
        - str: a string to indicate if the dates are updated successfully.
        """
        conn = connect(db)
        cursor = conn.cursor()

        if checkin_date:
            cursor.execute(
                "UPDATE hotels SET checkin_date = ? WHERE id = ?", (checkin_date, hotel_id)
            )
        if checkout_date:
            cursor.execute(
                "UPDATE hotels SET checkout_date = ? WHERE id = ?", (checkout_date, hotel_id)
            )

        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return f"Hotel {hotel_id} is successfully updated."
        else:
            conn.close()
            return f"Cannot find hotel with {hotel_id}."


    @mcp.tool(name=f"{GROUP_NAME}_cancel")
    def cancel_hotel(hotel_id: int) -> str:
        """
        Cancel hotel booking based on hotel ID.

        Parameters:
        - hotel_id (int): id of the hotel

        Returns:
        - str: a string to indicate if the hotel booking is canceled successfully.
        """
        conn = connect(db)
        cursor = conn.cursor()

        # make `booked` 0 to represent status of being canceled
        cursor.execute("UPDATE hotels SET booked = 0 WHERE id = ?", (hotel_id,))
        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return f"Booking with hotel {hotel_id} is canceled successfully."
        else:
            conn.close()
            return f"Can not find hotel {hotel_id}."
