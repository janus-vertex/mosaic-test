from typing import List, Tuple

import pandas
import psycopg2
from config import (
    SIMULATION_DATABASE_HOST,
    SIMULATION_DATABASE_PORT,
    SIMULATION_DATABASE_USER,
    SIMULATION_DATABASE_PASSWORD,
)


class SimulationDatabase:
    def __init__(self):
        self.conn = psycopg2.connect(
            database="matrix_simulation",
            host=SIMULATION_DATABASE_HOST,
            port=SIMULATION_DATABASE_PORT,
            user=SIMULATION_DATABASE_USER,
            password=SIMULATION_DATABASE_PASSWORD,
        )

    def execute_query(
        self, query: str, params: Tuple = None, fetch: bool = False
    ) -> List | None:
        """
        Execute a SQL query with error handling.

        Parameters
        ----------
        query : str
            SQL query to execute
        params : tuple, optional
            Optional parameters for the query
        fetch : bool, optional
            Whether to fetch and return results

        Returns
        -------
        List | None
            Query results if fetch=True, None otherwise
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)

            result = None
            if fetch:
                result = cursor.fetchall()
            else:
                self.conn.commit()

            cursor.close()
            return result

        except Exception as e:
            print(f"Error executing query: {e}")
            self.conn.rollback()
            return None

    def get_all_tables(self) -> List[str]:
        """
        Returns a list of all table names in the database.

        Returns
        -------
        List[str]
            List of table names as strings
        """
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """
        result = self.execute_query(query, fetch=True)
        return [table[0] for table in result] if result else []

    def close_connection(self):
        """
        Closes the database connection.
        """
        if self.conn:
            self.conn.close()

    def add_simulation_run(self, name: str, server_number: int, start_timestamp: float):
        """
        Adds a new simulation run to the simulation_runs table.

        Args:
            name (str): Name of the simulation
            server_number (int): Server number where the simulation ran
            start_timestamp (str): Timestamp when the simulation started

        Returns:
            int: ID of the created simulation run if successful, None otherwise
        """
        query = """
            INSERT INTO simulation_runs (name, server_number, start_timestamp)
            VALUES (%s, %s, %s)
            RETURNING id
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, (name, server_number, start_timestamp))
            result = cursor.fetchone()
            self.conn.commit()
            cursor.close()

            if result:
                return result[0]
            else:
                return None

        except Exception as e:
            print(f"Error adding simulation run: {e}")
            self.conn.rollback()
            return None

    def get_all_simulation_runs(self) -> pandas.DataFrame:
        """
        Retrieves all simulation runs from the database.

        Returns
        -------
        pandas.DataFrame
            DataFrame containing simulation run data
        """
        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT id, name, server_number, start_timestamp, end_timestamp
                FROM simulation_runs 
                ORDER BY start_timestamp DESC
            """
            )
            result = cursor.fetchall()
            cursor.close()
            df = pandas.DataFrame(
                result,
                columns=[
                    "id",
                    "name",
                    "server_number",
                    "start_timestamp",
                    "end_timestamp",
                ],
                dtype={
                    "id": int,
                    "name": str,
                    "server_number": int,
                    "start_timestamp": float,
                    "end_timestamp": float,
                },
            )
            return df

        except Exception as e:
            print(f"Error fetching simulation runs: {e}")
            return []

    def update_simulation_run_end_timestamp(
        self, simulation_run_id: int, end_timestamp: float
    ) -> bool:
        """
        Updates the end timestamp for a simulation run.

        Args:
            simulation_run_id (int): The ID of the simulation run to update
            end_timestamp (float): The end timestamp to set

        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            cursor = self.conn.cursor()
            query = """
                UPDATE simulation_runs 
                SET end_timestamp = %s 
                WHERE id = %s
            """
            cursor.execute(query, (end_timestamp, simulation_run_id))
            rows_affected = cursor.rowcount
            self.conn.commit()
            cursor.close()

            if rows_affected > 0:
                print(f"Updated end time for simulation run ID {simulation_run_id}")
                return True
            else:
                print(f"No simulation run found with ID {simulation_run_id}")
                return False

        except Exception as e:
            print(f"Error updating simulation end time: {e}")
            self.conn.rollback()
            return False

    def log_action(
        self,
        timestamp: float,
        simulation_run_id: int,
        action: str,
        station_code: int = None,
        bin_code: int = None,
    ) -> bool:
        """
        Logs an action to the simulation logs table.

        Parameters
        ----------
        timestamp : float
            The timestamp when the action occurred
        simulation_run_id : int
            The ID of the simulation run
        action : str
            Description of the action
        station_code : int, optional
            The station code if applicable
        bin_code : int, optional
            The bin code if applicable

        Returns
        -------
        bool
            True if logging was successful, False otherwise
        """
        cursor = self.conn.cursor()
        query = """
            INSERT INTO logs (timestamp, simulation_run_id, action, station_code, bin_code)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(
            query, (timestamp, simulation_run_id, action, station_code, bin_code)
        )
        self.conn.commit()
        cursor.close()
        return True


    def get_logs(self, simulation_run_id: int = None) -> pandas.DataFrame:
        """
        Retrieves simulation logs as a pandas DataFrame.

        Parameters
        ----------
        simulation_run_id : int, optional
            If provided, only logs for this simulation run will be returned.
            If None, all logs will be returned.

        Returns
        -------
        pandas.DataFrame
            DataFrame containing the logs data
        """
        try:

            filter_query = ""
            if simulation_run_id is not None:
                filter_query = f"WHERE simulation_run_id = {simulation_run_id}"

            query = f"""
                SELECT timestamp, simulation_run_id, action, station_code, bin_code
                FROM logs
                {filter_query}
                ORDER BY timestamp
            """
            cursor = self.conn.cursor()
            cursor.execute(query)

            columns = [
                "timestamp",
                "simulation_run_id",
                "action",
                "station_code",
                "bin_code",
            ]
            data = cursor.fetchall()
            cursor.close()

            return pandas.DataFrame(data, columns=columns)

        except Exception as e:
            print(f"Error retrieving logs: {e}")
            return pandas.DataFrame()


if __name__ == "__main__":
    db = SimulationDatabase()

    # Test add log
    db.log_action(12345.6, 2, "Test action", 1, 1)

    # Test log_action
    a = db.get_logs()
    db.close_connection()


