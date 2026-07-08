from sqlite3 import connect
from datetime import date, datetime
import pytz
from fastmcp import FastMCP
from langchain_core.runnables import RunnableConfig
from data.data_base import db

GROUP_NAME = "flights"

def register_flights_tools(mcp: FastMCP):
    """Register all the tools for flights management"""
    @mcp.tool(name=f"{GROUP_NAME}_fetch")
    def fetch_user_flight_information(config: RunnableConfig) -> list[dict]:
        """
        Get a passenger's flight and seat information based on their ID.

        Parameters:
        - config: configuration include passenger ID

        Return:
        - list of each ticket's details, flight and seat information, in a dictionary
        """
        configuration = config.get("configurable", {})
        passenger_id = configuration.get("passenger_id", None)
        if not passenger_id:
            raise ValueError("Passenger ID is required")

        conn = connect(db)
        cursor = conn.cursor()

        # SQL query, connect multiple tables to get info
        query = """
        SELECT 
            t.ticket_no, t.book_ref,
            f.flight_id, f.flight_no, f.departure_airport, f.arrival_airport, f.scheduled_departure, f.scheduled_arrival,
            bp.seat_no, tf.fare_conditions
        FROM 
            tickets t
            JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
            JOIN flights f ON tf.flight_id = f.flight_id
            JOIN boarding_passes bp ON bp.ticket_no = t.ticket_no AND bp.flight_id = f.flight_id
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
            departure_airport: str|None = None,
            arrival_airport: str|None = None,
            start_time: date|datetime|None = None,
            end_time: date|datetime|None = None,
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


    @mcp.tool(name=f"{GROUP_NAME}_update")
    def update_ticket_to_new_flight(
            ticket_no: str, new_flight_id: int, *, config: RunnableConfig
    ) -> str:
        """
        Update ticket flight information to new flight information as follow:
        1. check if passenger ID exists
        2. check flight info based on new flight ID, including departure airport, arrival airport, and scheduled departure
        3. make sure the gap between current time and the scheduled departure is no less than 3 hours
        4. verify if the original ticket is in the system
        5. verify is the passenger who made the request actually owns the ticket
        6. update the ticket flight information

        Parameters:
        - ticket_no (str)
        - new_flight_id (int)
        - config (RunnableConfig): configuration information including passenger_id

        Returns:
        - str: Message from operation results
        """
        configuration = config.get("configurable", {})
        passenger_id = configuration.get("passenger_id", None)
        if not passenger_id:
            raise ValueError("Passenger ID is required")

        conn = connect(db)
        cursor = conn.cursor()

        # check flight information
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

        # Set time zone and calculate the gap between current time and scheduled departure
        timezone = pytz.timezone("Etc/GMT-3")
        current_time = datetime.now(tz=timezone)
        departure_time = datetime.strptime(
            new_flight_dict["scheduled_departure"], "%Y-%m-%d %H:%M:%S.%f%z"
        )
        time_until = (departure_time - current_time).total_seconds()
        if time_until < (3 * 3600):
            return f"Not allowed to arrange a flight departing in less than 3 hours. The departure time is {departure_time}。"

        # validate the original ticket
        cursor.execute(
            "SELECT flight_id FROM ticket_flights WHERE ticket_no = ?", (ticket_no,)
        )
        current_flight = cursor.fetchone()
        if not current_flight:
            cursor.close()
            conn.close()
            return "Cannot find ticket with the given ticket no."

        # validate the ticket is owned by the passenger
        cursor.execute(
            "SELECT * FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
            (ticket_no, passenger_id),
        )
        current_ticket = cursor.fetchone()
        if not current_ticket:
            cursor.close()
            conn.close()
            return f"Current passenger id is {passenger_id}, not the owner of {ticket_no}."

        # update the flight
        cursor.execute(
            "UPDATE ticket_flights SET flight_id = ? WHERE ticket_no = ?",
            (new_flight_id, ticket_no),
        )
        conn.commit()

        cursor.close()
        conn.close()
        return "The ticket is updated with the new flight."


    @mcp.tool(name=f"{GROUP_NAME}_cancel")
    def cancel_ticket(ticket_no: str, *, config: RunnableConfig) -> str:
        """
        Cancel passenger ticket and delete from the database as follows:
        1. verify if passenger ID exists
        2. varify if the ticket is in the system
        3. varify if the passenger owns the ticket
        4. delete the ticket
        Parameters:
        - ticket_no (str)
        - config (RunnableConfig)
        Return:
        - str: message from operation results
        """
        configuration = config.get("configurable", {})
        passenger_id = configuration.get("passenger_id", None)
        if not passenger_id:
            raise ValueError("passenger ID is required")

        conn = connect(db)
        cursor = conn.cursor()

        # verify if passenger ID exists
        cursor.execute(
            "SELECT flight_id FROM ticket_flights WHERE ticket_no = ?", (ticket_no,)
        )
        existing_ticket = cursor.fetchone()
        if not existing_ticket:
            cursor.close()
            conn.close()
            return "Cannot find ticket with the given ticket no."

        # varify the the ticket is owned by the passenger
        cursor.execute(
            "SELECT flight_id FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
            (ticket_no, passenger_id),
        )
        current_ticket = cursor.fetchone()
        if not current_ticket:
            cursor.close()
            conn.close()
            return f"Current passenger id is {passenger_id}, not the owner of {ticket_no}."

        # delete ticket from database
        cursor.execute("DELETE FROM ticket_flights WHERE ticket_no = ?", (ticket_no,))
        conn.commit()

        cursor.close()
        conn.close()
        return "The ticket has been cancelled successfully."
