from sqlite3 import connect
from datetime import date, datetime
from fastmcp import FastMCP
from mcp_server.tools import db

GROUP_NAME = "car"

def register_car_tools(mcp: FastMCP):
    """Register all the tools for car rental"""

    @mcp.tool(name=f"{GROUP_NAME}_search")
    def search_car_rentals(
            location: str|None = None,
            name: str|None = None
    ) -> list[dict]:
        """
        Search car booking options based on location and the name of the car rental company.

        Parameters:
        - location (Optional[str]): location of the rental, default is None
        - name (Optional[str]): car rental company's name, default is None

        Returns:
        - list[dict]: list of car rental information
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

        conn.close()

        return [
            dict(zip([column[0] for column in cursor.description], row)) for row in results
        ]


    @mcp.tool(name=f"{GROUP_NAME}_book")
    def book_car_rental(rental_id: int) -> str:
        """
        Book car rental service based on id

        Parameters:
        - rental_id (int): id of car rental to book

        Returns:
        - str: whether the car rental is successfully booked
        """
        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute("UPDATE car_rentals SET booked = 1 WHERE id = ?", (rental_id,))
        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return f"Car rental {rental_id} is successfully booked"
        else:
            conn.close()
            return f"Car not find car rental {rental_id}"


    @mcp.tool(name=f"{GROUP_NAME}_update")
    def update_car_rental(
            rental_id: int,
            start_date: datetime|date|None = None,
            end_date: datetime|date|None = None,
    ) -> str:
        """
        Update the car rental's start date and end date based on id.

        Parameters:
        - rental_id (int): id of the car rental to update
        - start_date (Optional[Union[datetime, date]]): start date of the car rental, default is None
        - end_date (Optional[Union[datetime, date]]): end date of the car rental, default is None

        Returns:
            str: a string to indicate whether the update is successful
        """
        conn = connect(db)
        cursor = conn.cursor()

        if start_date:
            cursor.execute(
                "UPDATE car_rentals SET start_date = ? WHERE id = ?",
                (start_date, rental_id),
            )
        if end_date:
            cursor.execute(
                "UPDATE car_rentals SET end_date = ? WHERE id = ?", (end_date, rental_id)
            )

        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return f"汽车租赁 {rental_id} 成功更新。"
        else:
            conn.close()
            return f"未找到ID为 {rental_id} 的汽车租赁服务。"


    @mcp.tool(name=f"{GROUP_NAME}_cancel")
    def cancel_car_rental(rental_id: int) -> str:
        """
        Cancel car rental service based on ID.

        Parameters:
        - rental_id (int): id of the car rental to cancel

        Returns:
        - str: a string to indicate if the car rental is canceled successfully.
        """
        conn = connect(db)
        cursor = conn.cursor()

        cursor.execute("UPDATE car_rentals SET booked = 0 WHERE id = ?", (rental_id,))
        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return f"Car rental {rental_id} is cancelled successfully"
        else:
            conn.close()
            return f"Can not find car rental {rental_id}"
