from datetime import datetime, timedelta, timezone
from typing import List

import pandas
import plotly.graph_objects as go
import streamlit
from core.simulation_database import SimulationDatabase
from core.tc_database import MongoService


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

        # Show a progress bar 
        progress_bar = streamlit.progress(0)
        status_text = streamlit.empty()
        status_text.text("Please wait while the results are being loaded...")

        # Get the ID of the chosen simulation run
        selected_simulation = simulation_runs[
            simulation_runs["name_to_display"] == simulation_chosen
        ]
        simulation_run_id = selected_simulation["id"].iloc[0]

        # Get the logs of the chosen simulation run
        self.logs = simulation_database.get_logs_by_simulation_run(simulation_run_id)
        progress_bar.progress(12)

        # Get the parameters of the chosen simulation run
        simulation_parameters = simulation_database.get_parameters_by_simulation_run(
            simulation_run_id
        )
        progress_bar.progress(25)

        self.stations = self._parse_stations_from_string(
            simulation_parameters["stations_string"].iloc[0]
        )
        progress_bar.progress(37)

        log_start_timestamp = self.logs["timestamp"].min()
        log_end_timestamp = self.logs["timestamp"].max()
        self.duration_in_hours = (log_end_timestamp - log_start_timestamp) / 3600
        progress_bar.progress(50)

        # Connect to MongoDB to get movement data
        mongo_service = MongoService(
            server_number=selected_simulation["server_number"].iloc[0]
        )
        progress_bar.progress(62)

        self.movement_data = mongo_service.get_movement_data(
            start_timestamp=log_start_timestamp, end_timestamp=log_end_timestamp
        )
        progress_bar.progress(75)

        self._show_station_statistics()
        progress_bar.progress(87)

        self._show_handling_rate_statistics()
        progress_bar.progress(100)
        status_text.text("")

        # Close connections
        simulation_database.close_connection()
        mongo_service.close_connection()

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
        # Filter logs for 'Bin stored' actions
        # Filter logs for 'Bin stored' actions and compute bin presentation rates in one step
        station_counts = (
            self.logs[self.logs["action"] == "Bin stored"]
            .groupby("station_code")
            .size()
            .reset_index(name="bin_presentation_rate")
        )

        # Convert counts to rates and sort
        station_counts["bin_presentation_rate"] /= self.duration_in_hours
        station_counts = station_counts.sort_values(by="station_code").reset_index(
            drop=True
        )

        # Create station type mapping and apply it efficiently
        station_types = {station.code: station.type for station in self.stations}
        station_counts["type"] = station_counts["station_code"].map(station_types)

        # Pre-filter data for plotting
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
                textposition="auto",
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
                textposition="auto",
                name="Outbound",
            )
        )

        fig.update_layout(
            title="Bin Presentation Rate by Station",
            yaxis_title="Bin Presentation Rate (bins/hour)",
            xaxis=dict(
                title="Station Code",
                type="category",
                categoryorder="array",
                categoryarray=sorted(
                    station_counts["station_code"].unique(), key=lambda x: int(x)
                ),
            ),
            legend=dict(
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
        total_inbound_bin_presentation_rate = inbound_stations[
            "bin_presentation_rate"
        ].sum()
        total_outbound_bin_presentation_rate = outbound_stations[
            "bin_presentation_rate"
        ].sum()

        # Display metrics in two columns
        col1, col2 = streamlit.columns(2)
        col1.metric(
            label="Total inbound rate (bins/hour)",
            value=f"{total_inbound_bin_presentation_rate:.1f}",
        )
        col2.metric(
            label="Total outbound rate (bins/hour)",
            value=f"{total_outbound_bin_presentation_rate:.1f}",
        )

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
        # Calculate picking rates by skycar
        skycar_ids = self.movement_data["skycar_id"].unique()

        # Initialize arrays to store rates for each type
        retrieving_rates = []
        putaway_rates = []
        internal_rates = []

        station_pick_coords = [
            (station.pick_coords.x, station.pick_coords.y) for station in self.stations
        ]
        station_drop_coords = [
            (station.drop_coords.x, station.drop_coords.y) for station in self.stations
        ]

        # Create a tuple of (x, y) coordinates for faster lookup
        skycar_data_by_id = {}
        for skycar in skycar_ids:
            skycar_data_by_id[skycar] = self.movement_data[
                self.movement_data["skycar_id"] == skycar
            ]

        # Convert station coordinates to sets for faster lookups
        station_pick_coords_set = set(station_pick_coords)
        station_drop_coords_set = set(station_drop_coords)

        for skycar in skycar_ids:
            skycar_data = skycar_data_by_id[skycar]

            # Create coordinate tuples once
            coords = list(zip(skycar_data["x"], skycar_data["y"]))

            # Filter actions first
            logo_actions = skycar_data["action"].str.startswith("LOGO")
            logc_actions = skycar_data["action"].str.startswith("LOGC")

            # Calculate retrieving rate (LOGO at station coordinates)
            retrieving = sum(
                1
                for i, is_logo in enumerate(logo_actions)
                if is_logo and coords[i] in station_pick_coords_set
            )
            retrieving_rates.append(retrieving / self.duration_in_hours)

            # Calculate putaway rate (LOGC at station coordinates)
            putaway = sum(
                1
                for i, is_logc in enumerate(logc_actions)
                if is_logc and coords[i] in station_drop_coords_set
            )
            putaway_rates.append(putaway / self.duration_in_hours)

            # Calculate internal rate (remaining LOGO operations)
            total_logo = logo_actions.sum()
            internal = total_logo - retrieving - putaway
            internal_rates.append(internal / self.duration_in_hours)

        # Create stacked bar chart
        fig = go.Figure(
            data=[
                go.Bar(
                    name="Retrieving",
                    x=skycar_ids,
                    y=retrieving_rates,
                    text=[f"{rate:.1f}" for rate in retrieving_rates],
                    textposition="auto",
                ),
                go.Bar(
                    name="Putaway",
                    x=skycar_ids,
                    y=putaway_rates,
                    text=[f"{rate:.1f}" for rate in putaway_rates],
                    textposition="auto",
                ),
                go.Bar(
                    name="Internal",
                    x=skycar_ids,
                    y=internal_rates,
                    text=[f"{rate:.1f}" for rate in internal_rates],
                    textposition="auto",
                ),
            ]
        )

        fig.update_layout(
            title="Bin Handling Rate by Skycar",
            yaxis_title="Bin Handling Rate (bins/hour)",
            barmode="stack",
            xaxis=dict(
                title="Skycar ID",
                type="category",
                categoryorder="array",
                categoryarray=sorted(skycar_ids, key=lambda x: int(x)),
            ),
        )
        streamlit.plotly_chart(fig)

        # Calculate and display total metrics
        total_retrieving = sum(retrieving_rates)
        total_putaway = sum(putaway_rates)
        total_internal = sum(internal_rates)

        col1, col2, col3 = streamlit.columns(3)
        col1.metric(
            "Total retrieving rate (bins/hour)",
            f"{total_retrieving:.1f}",
        )
        col2.metric(
            "Total putaway rate (bins/hour)",
            f"{total_putaway:.1f}",
        )
        col3.metric(
            "Total internal rate (bins/hour)",
            f"{total_internal:.1f}",
        )

        col1, col2, col3 = streamlit.columns(3)
        col1.metric(
            "Average retrieving rate (bins/hour)",
            f"{total_retrieving / len(skycar_ids):.1f}",
        )
        col2.metric(
            "Average putaway rate (bins/hour)",
            f"{total_putaway / len(skycar_ids):.1f}",
        )
        col3.metric(
            "Average internal rate (bins/hour)",
            f"{total_internal / len(skycar_ids):.1f}",
        )
