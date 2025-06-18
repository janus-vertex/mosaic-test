from typing import List, Optional
import pandas
from sqlalchemy import create_engine, text, Column, Integer, String, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from core.config import (
    SIMULATION_DATABASE_HOST,
    SIMULATION_DATABASE_PORT,
    SIMULATION_DATABASE_USER,
    SIMULATION_DATABASE_PASSWORD,
)
from urllib.parse import quote_plus
import time

Base = declarative_base()


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    server_number = Column(Integer)
    start_timestamp = Column(Float, nullable=True)
    end_timestamp = Column(Float, nullable=True)


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(Float)
    simulation_run_id = Column(Integer)
    action = Column(String)
    station_code = Column(Integer, nullable=True)
    bin_code = Column(Integer, nullable=True)


class Parameter(Base):
    __tablename__ = "parameters"

    id = Column(Integer, primary_key=True)
    simulation_run_id = Column(Integer)
    simulation_name = Column(String, nullable=True)
    simulation_duration = Column(Integer, nullable=True)
    inbound_bins_per_order = Column(Integer, nullable=True)
    outbound_bins_per_order = Column(Integer, nullable=True)
    inbound_orders_per_hour = Column(Integer, nullable=True)
    outbound_orders_per_hour = Column(Integer, nullable=True)
    number_of_skycars = Column(Integer, nullable=True)
    inbound_handling_time = Column(Integer, nullable=True)
    outbound_handling_time = Column(Integer, nullable=True)
    pareto_p = Column(Float, nullable=True)
    pareto_q = Column(Float, nullable=True)
    number_of_bins = Column(Integer, nullable=True)
    stations_string = Column(String, nullable=True)
    timestamp = Column(Float, nullable=True)
    duration_string = Column(String, nullable=True)


class SimulationDatabase:
    def __init__(self):
        # URL encode the username and password to handle special characters
        database_url = (
            f"postgresql://{quote_plus(SIMULATION_DATABASE_USER)}:{quote_plus(SIMULATION_DATABASE_PASSWORD)}"
            f"@{SIMULATION_DATABASE_HOST}:{SIMULATION_DATABASE_PORT}/matrix_simulation"
        )
        self.engine = create_engine(database_url)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        Base.metadata.create_all(self.engine)

    def add_simulation_run(self, name: str, server_number: int) -> int | None:
        """
        Adds a new simulation run to the simulation_runs table.
        """
        try:
            sim_run = SimulationRun(name=name, server_number=server_number)
            self.session.add(sim_run)
            self.session.commit()
            return sim_run.id
        except SQLAlchemyError as e:
            print(f"Error adding simulation run: {e}")
            self.session.rollback()
            return None

    def add_simulation_parameters(
        self, simulation_run_id: int, parameters: dict
    ) -> int | None:
        """
        Adds new simulation parameters to the parameters table.
        """
        try:
            param = Parameter(
                **parameters, simulation_run_id=simulation_run_id, timestamp=time.time()
            )
            self.session.add(param)
            self.session.commit()
            return param.id
        except SQLAlchemyError as e:
            print(f"Error adding simulation parameters: {e}")
            self.session.rollback()
            return None

    def get_simulation_runs_by_timestamp_range(
        self, timestamp1: float, timestamp2: float
    ) -> pandas.DataFrame:
        """
        Retrieves simulation runs within a specified timestamp range.

        Parameters
        ----------
        timestamp1 : float
            The start timestamp of the range
        timestamp2 : float
            The end timestamp of the range

        Returns
        -------
        pandas.DataFrame
            A DataFrame of simulation runs within the specified timestamp range
        """
        try:
            query = text(
                f"""
                SELECT * FROM 
                get_simulation_runs_by_timestamp_range({timestamp1}, {timestamp2})
                """
            )

            result = self.session.execute(query)

            # Convert the result to a pandas DataFrame
            df = pandas.DataFrame(result.fetchall())

            # If results were found, set the column names
            if not df.empty:
                df.columns = result.keys()

            return df
        except SQLAlchemyError as e:
            print(f"Error retrieving simulation runs: {e}")
            return pandas.DataFrame()

    def get_logs_by_simulation_run(self, simulation_run_id: int) -> pandas.DataFrame:
        """
        Retrieves logs for a specific simulation run.

        Parameters
        ----------
        simulation_run_id : int
            The ID of the simulation run

        Returns
        -------
        pandas.DataFrame
            A DataFrame of logs for the specified simulation run
        """
        try:
            query = text(
                f"""
                SELECT * FROM get_logs_by_simulation_run({simulation_run_id})
                """
            )

            result = self.session.execute(query)
            df = pandas.DataFrame(result.fetchall())

            if not df.empty:
                df.columns = result.keys()

            return df
        except SQLAlchemyError as e:
            print(f"Error retrieving logs: {e}")
            return pandas.DataFrame()

    def get_parameters_by_simulation_run(
        self, simulation_run_id: int
    ) -> pandas.DataFrame:
        """
        Retrieves parameters for a specific simulation run.

        Parameters
        ----------
        simulation_run_id : int
            The ID of the simulation run

        Returns
        -------
        pandas.DataFrame
            A DataFrame of parameters for the specified simulation run
        """
        try:
            query = text(
                f"""
                SELECT * FROM public.parameters
                WHERE simulation_run_id = {simulation_run_id}
                """
            )

            result = self.session.execute(query)
            df = pandas.DataFrame(result.fetchall())

            if not df.empty:
                df.columns = result.keys()

            return df
        except SQLAlchemyError as e:
            print(f"Error retrieving parameters: {e}")
            return pandas.DataFrame()

    def close_connection(self):
        """Closes the database connection."""
        self.session.close()
        self.engine.dispose()
