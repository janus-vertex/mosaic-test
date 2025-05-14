from datetime import datetime, timedelta, timezone
from typing import List

import plotly.graph_objects as go
import streamlit
from core.simulation_database import SimulationDatabase


class Coordinates:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y


class Station:
    def __init__(
        self, code: int, type_: str, drop_coords: Coordinates, pick_coords: Coordinates
    ):
        self.code = code
        self.type = type_
        self.drop_coords = drop_coords
        self.pick_coords = pick_coords


class ResultUI:
    def __init__(self):
        pass

    def show(self):
        streamlit.write("## Results")

        # Choose date range for the list of simulation runs
        date_range = streamlit.date_input(
            "Simulation start date range",
            value=(datetime.today() - timedelta(days=7), datetime.today()),
            format="DD/MM/YYYY",
        )

        if len(date_range) == 1:
            start_timestamp = datetime.combine(
                date_range[0], datetime.min.time()
            ).timestamp()
            end_timestamp = datetime.combine(
                date_range[0] + timedelta(days=366), datetime.max.time()
            ).timestamp()

        elif len(date_range) == 2:
            start_timestamp = datetime.combine(
                date_range[0], datetime.min.time()
            ).timestamp()
            end_timestamp = datetime.combine(
                date_range[1], datetime.max.time()
            ).timestamp()

        # Get the list of simulation runs within the chosen date range
        simulation_database = SimulationDatabase()
        simulation_runs = simulation_database.get_simulation_runs_by_timestamp_range(
            start_timestamp, end_timestamp
        )

        if len(simulation_runs) == 0:
            streamlit.warning("No simulation runs found in the chosen date range.")
            return

        simulation_runs["name_to_display"] = (
            simulation_runs["name"]
            + " ➨ "
            + simulation_runs["start_timestamp"].apply(
                lambda x: datetime.fromtimestamp(
                    x, tz=timezone(timedelta(hours=8))
                ).strftime("%Y-%m-%d %H:%M:%S")
            )
            + " ➨ Server "
            + simulation_runs["server_number"].astype(str)
        )

        # Choose a simulation from the list
        simulation_chosen = streamlit.selectbox(
            "Select simulation",
            simulation_runs["name_to_display"].tolist(),
            index=None,
            placeholder="Choose a simulation...",
        )
        if simulation_chosen is None:
            return

        # Get the ID of the chosen simulation run
        selected_simulation = simulation_runs[
            simulation_runs["name_to_display"] == simulation_chosen
        ]
        simulation_run_id = selected_simulation["id"].iloc[0]

        # Get the logs of the chosen simulation run
        self.logs = simulation_database.get_logs_by_simulation_run(simulation_run_id)

        # Get the parameters of the chosen simulation run
        simulation_parameters = simulation_database.get_parameters_by_simulation_run(
            simulation_run_id
        )

        self.stations = self._parse_stations_from_string(
            simulation_parameters["stations_string"].iloc[0]
        )

        self._show_station_statistics()

        self._show_handling_rate_statistics()

    def _parse_stations_from_string(self, station_string: str) -> List[Station]:
        """
        Parse a string representation of stations into a list of Station objects.

        Example input: "1I:D(x1y44)P(x1y44);2O:D(x4y44)P(x4y44)"

        Where:
        - 1I: Station code (1) and type (I for Inbound, O for Outbound)
        - D(x1y44): Drop coordinates (x=1, y=44)
        - P(x1y44): Pick coordinates (x=1, y=44)
        - Stations are separated by semicolons
        """
        stations = []

        # Split the string by semicolons to get individual station definitions
        station_definitions = station_string.split(";")

        for station_def in station_definitions:
            if not station_def.strip():
                continue

            # Split the station definition into code/type and coordinates
            parts = station_def.split(":")
            if len(parts) != 2:
                continue

            # Extract station code and type
            code_type = parts[0]
            if len(code_type) < 2:
                continue

            code = int(code_type[:-1])
            type_ = code_type[-1]

            # Extract coordinates
            coords_part = parts[1]

            # Extract drop coordinates
            drop_match = coords_part.find("D(")
            if drop_match != -1:
                drop_coords_str = coords_part[
                    drop_match + 2 : coords_part.find(")", drop_match)
                ]
                drop_x = int(drop_coords_str.split("y")[0].replace("x", ""))
                drop_y = int(drop_coords_str.split("y")[1])
                drop_coords = Coordinates(drop_x, drop_y)
            else:
                continue

            # Extract pick coordinates
            pick_match = coords_part.find("P(")
            if pick_match != -1:
                pick_coords_str = coords_part[
                    pick_match + 2 : coords_part.find(")", pick_match)
                ]
                pick_x = int(pick_coords_str.split("y")[0].replace("x", ""))
                pick_y = int(pick_coords_str.split("y")[1])
                pick_coords = Coordinates(pick_x, pick_y)
            else:
                continue

            # Create and add the station
            station = Station(code, type_, drop_coords, pick_coords)
            stations.append(station)

        return stations

    def _show_station_statistics(self):
        duration_in_hours = (
            self.logs["timestamp"].max() - self.logs["timestamp"].min()
        ) / 3600

        # Filter logs for 'Bin stored' actions
        bin_stored_logs = self.logs[self.logs["action"] == "Bin stored"]

        # Count entries per station to get bin presentation rate per station
        station_counts = bin_stored_logs["station_code"].value_counts().reset_index()
        station_counts.columns = ["station_code", "bin_presentation_rate"]
        station_counts["bin_presentation_rate"] /= duration_in_hours
        station_counts = station_counts.sort_values(by="station_code").reset_index(
            drop=True
        )
        # Add station type information to the dataframe
        station_types = {station.code: station.type for station in self.stations}
        station_counts["type"] = station_counts["station_code"].map(station_types)

        # Create bar chart
        # Create separate traces for inbound and outbound stations
        inbound_stations = station_counts[station_counts["type"] == "I"]
        outbound_stations = station_counts[station_counts["type"] == "O"]

        fig = go.Figure()

        # Add inbound stations with pattern
        fig.add_trace(
            go.Bar(
                x=inbound_stations["station_code"],
                y=inbound_stations["bin_presentation_rate"],
                text=[
                    f"{rate:.1f}" for rate in inbound_stations["bin_presentation_rate"]
                ],
                textposition="outside",
                name="Inbound",
            )
        )

        # Add outbound stations without pattern
        fig.add_trace(
            go.Bar(
                x=outbound_stations["station_code"],
                y=outbound_stations["bin_presentation_rate"],
                text=[
                    f"{rate:.1f}" for rate in outbound_stations["bin_presentation_rate"]
                ],
                textposition="outside",
                name="Outbound",
            )
        )

        fig.update_layout(
            title="Bin Presentation Rate by Station",
            yaxis_title="Bin Presentation Rate (bins/hour)",
            xaxis=dict(
                title="Station Code",
                type="category",
            ),
            legend=dict(
                title="Station Type",
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
            ),
        )
        streamlit.plotly_chart(fig)

        # Calculate average bin presentation rates
        average_inbound_bin_presentation_rate = inbound_stations[
            "bin_presentation_rate"
        ].mean()
        average_outbound_bin_presentation_rate = outbound_stations[
            "bin_presentation_rate"
        ].mean()

        # Display metrics in two columns
        col1, col2 = streamlit.columns(2)

        col1.metric(
            label="Average inbound rate (bins/hour)",
            value=f"{average_inbound_bin_presentation_rate:.1f}",
        )

        col2.metric(
            label="Average outbound rate (bins/hour)",
            value=f"{average_outbound_bin_presentation_rate:.1f}",
        )


    def _show_handling_rate_statistics(self):
        pass

