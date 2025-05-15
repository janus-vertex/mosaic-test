from typing import List, Optional
import pandas
from sqlalchemy import create_engine, text, Column, Integer, String, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from config import (
    SIMULATION_DATABASE_HOST,
    SIMULATION_DATABASE_PORT,
    SIMULATION_DATABASE_USER,
    SIMULATION_DATABASE_PASSWORD,
)
from urllib.parse import quote_plus

Base = declarative_base()


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    server_number = Column(Integer)
    start_timestamp = Column(Float)
    end_timestamp = Column(Float, nullable=True)


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(Float)
    simulation_run_id = Column(Integer)
    action = Column(String)
    station_code = Column(Integer, nullable=True)
    bin_code = Column(Integer, nullable=True)


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

    def get_all_tables(self) -> List[str]:
        """Returns a list of all table names in the database."""
        query = text(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """
        )
        result = self.session.execute(query)
        return [row[0] for row in result]

    def get_all_simulation_runs(self) -> pandas.DataFrame:
        """Retrieves all simulation runs from the database."""
        try:
            result = (
                self.session.query(SimulationRun)
                .order_by(SimulationRun.start_timestamp.desc())
                .all()
            )
            data = [
                (r.id, r.name, r.server_number, r.start_timestamp, r.end_timestamp)
                for r in result
            ]
            return pandas.DataFrame(
                data,
                columns=[
                    "id",
                    "name",
                    "server_number",
                    "start_timestamp",
                    "end_timestamp",
                ],
            )
        except SQLAlchemyError as e:
            print(f"Error fetching simulation runs: {e}")
            return pandas.DataFrame()

    def update_simulation_run_timestamp(
        self,
        simulation_run_id: int,
        start_timestamp: float = None,
        end_timestamp: float = None,
    ) -> bool:
        """Updates the end timestamp for a simulation run."""
        try:
            sim_run = (
                self.session.query(SimulationRun)
                .filter_by(id=simulation_run_id)
                .first()
            )
            if sim_run:
                if start_timestamp is not None:
                    sim_run.start_timestamp = start_timestamp
                elif end_timestamp is not None:
                    sim_run.end_timestamp = end_timestamp
                else:
                    raise ValueError("No timestamp provided")
                self.session.commit()
                return True
            print(f"No simulation run found with ID {simulation_run_id}")
            return False
        except SQLAlchemyError as e:
            print(f"Error updating simulation time: {e}")
            self.session.rollback()
            return False

    def log_action(
        self,
        timestamp: float,
        simulation_run_id: int,
        action: str,
        station_code: Optional[int] = None,
        bin_code: Optional[int] = None,
    ) -> bool:
        """Logs an action to the simulation logs table."""
        try:
            log = Log(
                timestamp=timestamp,
                simulation_run_id=simulation_run_id,
                action=action,
                station_code=station_code,
                bin_code=bin_code,
            )
            self.session.add(log)
            self.session.commit()
            return True
        except SQLAlchemyError as e:
            print(f"Error logging action: {e}")
            self.session.rollback()
            return False

    def get_logs(self, simulation_run_id: Optional[int] = None) -> pandas.DataFrame:
        """Retrieves simulation logs as a pandas DataFrame."""
        try:
            query = self.session.query(Log)
            if simulation_run_id is not None:
                query = query.filter_by(simulation_run_id=simulation_run_id)
            query = query.order_by(Log.timestamp)

            result = query.all()
            data = [
                (r.timestamp, r.simulation_run_id, r.action, r.station_code, r.bin_code)
                for r in result
            ]
            return pandas.DataFrame(
                data,
                columns=[
                    "timestamp",
                    "simulation_run_id",
                    "action",
                    "station_code",
                    "bin_code",
                ],
            )
        except SQLAlchemyError as e:
            print(f"Error retrieving logs: {e}")
            return pandas.DataFrame()

    def close_connection(self):
        """Closes the database connection."""
        self.session.close()
        self.engine.dispose()
