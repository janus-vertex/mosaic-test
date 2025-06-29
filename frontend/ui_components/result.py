from datetime import datetime, timedelta, timezone
from typing import Dict, List

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
        # Initialize session state cache if it doesn't exist
        if "simulation_cache" not in streamlit.session_state:
            streamlit.session_state.simulation_cache = {}

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

        # Initialize connection objects
        simulation_database = None
        mongo_service = None

        try:
            # Get the list of simulation runs within the chosen date range
            simulation_database = SimulationDatabase()
            simulation_runs = (
                simulation_database.get_simulation_runs_by_timestamp_range(
                    start_timestamp, end_timestamp
                )
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

            # Get the ID of the chosen simulation run
            selected_simulation = simulation_runs[
                simulation_runs["name_to_display"] == simulation_chosen
            ]
            simulation_run_id = selected_simulation["id"].iloc[0]

            # Check if simulation data is already cached in session state
            cache_key = f"sim_{simulation_run_id}"
            if cache_key in streamlit.session_state.simulation_cache:
                cached_data = streamlit.session_state.simulation_cache[cache_key]
                self.logs = cached_data["logs"]
                self.movement_data = cached_data["movement_data"]
            else:
                # Load data from databases
                self.logs = simulation_database.get_logs_by_simulation_run(
                    simulation_run_id
                )

                # Connect to MongoDB to get movement data
                mongo_service = MongoService(
                    server_number=selected_simulation["server_number"].iloc[0]
                )
                self.movement_data = mongo_service.get_movement_data(
                    start_timestamp=self.logs["timestamp"].min(),
                    end_timestamp=self.logs["timestamp"].max(),
                )

                # Cache the data in session state
                streamlit.session_state.simulation_cache[cache_key] = {
                    "logs": self.logs,
                    "movement_data": self.movement_data,
                }

            progress_bar.progress(50)

            log_start_timestamp = self.logs["timestamp"].min()
            log_end_timestamp = self.logs["timestamp"].max()
            self.duration_in_hours = (log_end_timestamp - log_start_timestamp) / 3600

            self._get_normal_operation_ranges()

            self._show_simulation_durations()

            # Get the parameters of the chosen simulation run
            simulation_parameters = (
                simulation_database.get_parameters_by_simulation_run(simulation_run_id)
            )
            self.stations = self._parse_stations_from_string(
                simulation_parameters["stations_string"].iloc[0]
            )

            progress_bar.progress(75)

            is_normal_operation_only = streamlit.toggle(
                "Show normal operation only", value=False
            )
            self._show_station_statistics(
                is_normal_operation_only=is_normal_operation_only
            )
            progress_bar.progress(83)

            self._show_handling_rate_statistics(
                is_normal_operation_only=is_normal_operation_only
            )
            progress_bar.progress(91)

            self._show_bin_presentation_rate_over_time()
            progress_bar.progress(100)

        # Clean up connections
        finally:
            if simulation_database is not None:
                simulation_database.close_connection()

            if mongo_service is not None:
                mongo_service.close_connection()

    def _get_normal_operation_ranges(self):
        normal_operation_start_timestamps = self.logs[
            (self.logs["action"] == "Normal operation starts")
        ]["timestamp"].tolist()[::-1]

        normal_operation_end_timestamps = self.logs[
            (self.logs["action"] == "Advance order starts")
            | (self.logs["action"] == "Simulation ends")
        ]["timestamp"].tolist()[::-1]

        normal_operation_ranges = []
        for start in normal_operation_start_timestamps:
            end = next(
                (i for i in normal_operation_end_timestamps if i > start),
                self.logs["timestamp"].min(),
            )
            normal_operation_ranges.append((start, end))

        self.normal_operation_ranges = normal_operation_ranges
        self.normal_operation_duration_in_hours = sum(
            (end - start) / 3600 for start, end in normal_operation_ranges
        )

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

    def _show_simulation_durations(self):
        streamlit.write("#### Simulation durations")
        col1, col2 = streamlit.columns(2)
        col1.metric(
            "Whole simulation",
            self._convert_to_readable_time(self.duration_in_hours),
        )
        col2.metric(
            "Normal operations only",
            self._convert_to_readable_time(self.normal_operation_duration_in_hours),
        )

    @staticmethod
    def _convert_to_readable_time(input_hours: float) -> str:
        hours = int(input_hours)
        minutes = int(input_hours * 60 % 60)

        hours_text = f"{hours}h" if hours > 0 else ""
        minutes_text = f"{minutes}m" if minutes > 0 else ""
        return f"{hours_text} {minutes_text}"

    def _show_station_statistics(self, is_normal_operation_only: bool):
        # Filter logs for 'Bin stored' actions and compute bin presentation rates in one step
        if is_normal_operation_only:
            logs = pandas.DataFrame()
            for start, end in self.normal_operation_ranges:
                logs = pandas.concat(
                    [
                        logs,
                        self.logs[
                            (self.logs["timestamp"] >= start)
                            & (self.logs["timestamp"] <= end)
                        ],
                    ]
                )
            duration_in_hours = self.normal_operation_duration_in_hours
        else:
            logs = self.logs
            duration_in_hours = self.duration_in_hours

        if logs.empty:
            streamlit.warning(
                "No simulation logs from normal operations in this simulation."
            )
            return

        station_counts = (
            logs[logs["action"] == "Bin stored"]
            .groupby("station_code")
            .size()
            .reset_index(name="bin_presentation_rate")
        )

        # Convert counts to rates and sort
        station_counts["bin_presentation_rate"] /= duration_in_hours
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

        # Display metrics in a dataframe
        rates_df = pandas.DataFrame(
            {
                "Average": [
                    f"{average_inbound_bin_presentation_rate:.1f}",
                    f"{average_outbound_bin_presentation_rate:.1f}",
                ],
                "Total": [
                    f"{total_inbound_bin_presentation_rate:.1f}",
                    f"{total_outbound_bin_presentation_rate:.1f}",
                ],
            },
            index=["Inbound rate (bins/hour)", "Outbound rate (bins/hour)"],
        )

        streamlit.dataframe(
            rates_df,
            use_container_width=True,
            hide_index=False,
        )

    def _show_handling_rate_statistics(self, is_normal_operation_only: bool):
        if is_normal_operation_only:
            # Filter movement data to only include records within normal operation time ranges
            movement_data = pandas.DataFrame()
            for start, end in self.normal_operation_ranges:
                filtered_data = self.movement_data[
                    (self.movement_data["completed_at"] >= start)
                    & (self.movement_data["completed_at"] <= end)
                ]
                movement_data = pandas.concat([movement_data, filtered_data])
            duration_in_hours = self.normal_operation_duration_in_hours
        else:
            movement_data = self.movement_data
            duration_in_hours = self.duration_in_hours

        if movement_data.empty:
            streamlit.warning(
                "No skycar movement data from normal operations in this simulation."
            )
            return

        # Calculate picking rates by skycar
        skycar_ids = movement_data["skycar_id"].unique()

        # Initialize arrays to store rates for each type
        retrieving_rates = []
        putaway_rates = []
        internal_normal_rates = []
        internal_advance_rates = []

        station_pick_coords = [
            (station.pick_coords.x, station.pick_coords.y) for station in self.stations
        ]
        station_drop_coords = [
            (station.drop_coords.x, station.drop_coords.y) for station in self.stations
        ]

        # Create a tuple of (x, y) coordinates for faster lookup
        skycar_data_by_id: Dict[int, pandas.DataFrame] = {}
        for skycar in skycar_ids:
            skycar_data_by_id[skycar] = movement_data[
                movement_data["skycar_id"] == skycar
            ]

        # Convert station coordinates to sets for faster lookups
        station_pick_coords_set = set(station_pick_coords)
        station_drop_coords_set = set(station_drop_coords)

        for skycar in skycar_ids:
            skycar_data = skycar_data_by_id[skycar]

            # Filter actions first
            # Create masks for LOGO and LOGC actions with their timestamps
            logo_actions = skycar_data["action"].str.startswith("LOGO")
            logc_actions = skycar_data["action"].str.startswith("LOGC")
            logo_timestamps = skycar_data.loc[logo_actions, "completed_at"]
            logc_timestamps = skycar_data.loc[logc_actions, "completed_at"]

            # Create a DataFrame with coordinates for easier indexing and filtering
            coords = pandas.DataFrame(
                {"coord": zip(skycar_data["x"], skycar_data["y"])},
                index=skycar_data.index,
            )

            # Calculate retrieving rate (LOGO at station coordinates)
            retrieving = sum(
                1
                for i in logo_timestamps.index
                if coords.loc[i]["coord"] in station_pick_coords_set
            )
            retrieving_rates.append(retrieving / duration_in_hours)

            # Calculate putaway rate (LOGC at station coordinates)
            putaway = sum(
                1
                for i in logc_timestamps.index
                if coords.loc[i]["coord"] in station_drop_coords_set
            )
            putaway_rates.append(putaway / duration_in_hours)

            # Calculate internal rate (remaining LOGO operations)
            total_logo = len(logo_timestamps)
            logo_in_normal_operations = sum(
                1
                for _, t in logo_timestamps.items()
                if any(start <= t <= end for start, end in self.normal_operation_ranges)
            )
            internal_normal = logo_in_normal_operations - retrieving - putaway
            internal_normal_rates.append(internal_normal / duration_in_hours)
            internal_advance_rates.append(
                (total_logo - logo_in_normal_operations) / duration_in_hours
            )

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
                    name="Internal (Normal Ops.)",
                    x=skycar_ids,
                    y=internal_normal_rates,
                    text=[f"{rate:.1f}" for rate in internal_normal_rates],
                    textposition="auto",
                ),
                go.Bar(
                    name="Internal (Advance Ops.)",
                    x=skycar_ids,
                    y=internal_advance_rates,
                    text=[f"{rate:.1f}" for rate in internal_advance_rates],
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
        total_internal_normal = sum(internal_normal_rates)
        total_internal_advance = sum(internal_advance_rates)

        # Display metrics in a dataframe
        rates_df = pandas.DataFrame(
            {
                "Average": [
                    f"{total_retrieving / len(skycar_ids):.1f}",
                    f"{total_putaway / len(skycar_ids):.1f}",
                    f"{(total_internal_normal + total_internal_advance) / len(skycar_ids):.1f}",
                    f"{total_internal_normal / len(skycar_ids):.1f}",
                    f"{total_internal_advance / len(skycar_ids):.1f}",
                ],
                "Total": [
                    f"{total_retrieving:.1f}",
                    f"{total_putaway:.1f}",
                    f"{total_internal_normal + total_internal_advance:.1f}",
                    f"{total_internal_normal:.1f}",
                    f"{total_internal_advance:.1f}",
                ],
            },
            index=[
                "Retrieving rate (bins/hour)",
                "Putaway rate (bins/hour)",
                "Internal rate (bins/hour)",
                " ➨ Internal rate - normal ops. (bins/hour)",
                " ➨ Internal rate - advance ops. (bins/hour)",
            ],
        )

        streamlit.dataframe(
            rates_df,
            use_container_width=True,
            hide_index=False,
        )

    def _show_bin_presentation_rate_over_time(self):
        streamlit.write("#### Bin Presentation Rate Over Time")
        
        # Filter logs for 'Bin stored' actions
        bin_stored_logs = self.logs[self.logs["action"] == "Bin stored"].copy()
        
        if bin_stored_logs.empty:
            streamlit.warning("No 'Bin stored' logs found in this simulation.")
            return
        
        # Convert timestamp to datetime for easier manipulation
        bin_stored_logs["datetime"] = pandas.to_datetime(
            bin_stored_logs["timestamp"], unit="s"
        )
        
        # Create 10-minute intervals
        bin_stored_logs["interval"] = bin_stored_logs["datetime"].dt.floor("10min")
        
        # Group by interval and station_code, then count occurrences
        interval_station_counts = (
            bin_stored_logs.groupby(["interval", "station_code"])
            .size()
            .reset_index(name="count")
        )
        
        # Convert counts to rates (bins per hour): 10 minutes = 1/6 hour, so multiply by 6
        interval_station_counts["rate"] = interval_station_counts["count"] * 6
        
        # Get all unique intervals and stations for complete data
        all_intervals = pandas.date_range(
            start=bin_stored_logs["interval"].min(),
            end=bin_stored_logs["interval"].max(),
            freq="10min"
        )
        all_stations = sorted([station.code for station in self.stations])
        
        # Create a complete DataFrame with all interval-station combinations
        complete_data = []
        for interval in all_intervals:
            for station in all_stations:
                rate = interval_station_counts[
                    (interval_station_counts["interval"] == interval) &
                    (interval_station_counts["station_code"] == station)
                ]["rate"]
                rate_value = rate.iloc[0] if not rate.empty else 0
                complete_data.append({
                    "interval": interval,
                    "station_code": station,
                    "rate": rate_value
                })
        
        complete_df = pandas.DataFrame(complete_data)
        
        # Create line plot
        fig = go.Figure()
        
        # Add a line trace for each station
        for station in all_stations:
            station_data = complete_df[complete_df["station_code"] == station]
            fig.add_trace(
                go.Scatter(
                    name=f"Station {station}",
                    x=station_data["interval"],
                    y=station_data["rate"],
                    mode="lines+markers",
                    line=dict(width=2),
                    marker=dict(size=4),
                )
            )
        
        # Calculate advance order periods (complement of normal operation ranges)
        log_start_timestamp = self.logs["timestamp"].min()
        log_end_timestamp = self.logs["timestamp"].max()
        
        advance_order_ranges = []
        
        # Sort normal operation ranges by start time
        sorted_normal_ranges = sorted(self.normal_operation_ranges, key=lambda x: x[0])
        
        # Add period before first normal operation (if any)
        if sorted_normal_ranges and sorted_normal_ranges[0][0] > log_start_timestamp:
            advance_order_ranges.append((log_start_timestamp, sorted_normal_ranges[0][0]))
        
        # Add periods between normal operations
        for i in range(len(sorted_normal_ranges) - 1):
            current_end = sorted_normal_ranges[i][1]
            next_start = sorted_normal_ranges[i + 1][0]
            if next_start > current_end:
                advance_order_ranges.append((current_end, next_start))
        
        # Add period after last normal operation (if any)
        if sorted_normal_ranges and sorted_normal_ranges[-1][1] < log_end_timestamp:
            advance_order_ranges.append((sorted_normal_ranges[-1][1], log_end_timestamp))
        
        # Add advance order period highlights
        y_max = complete_df.groupby("interval")["rate"].sum().max()
        if y_max > 0:
            for start_ts, end_ts in advance_order_ranges:
                start_dt = pandas.to_datetime(start_ts, unit="s")
                end_dt = pandas.to_datetime(end_ts, unit="s")
                fig.add_vrect(
                    x0=start_dt,
                    x1=end_dt,
                    fillcolor="red",
                    opacity=0.2,
                    layer="below",
                    line_width=0,
                )
        
        fig.update_layout(
            title="Bin Presentation Rate Over Time (10-minute intervals)",
            xaxis_title="Time",
            yaxis_title="Bin Presentation Rate (bins/hour)",
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02,
            ),
            annotations=[
                dict(
                    x=1.02,
                    y=0.5,
                    xref="paper",
                    yref="paper",
                    text="<b>Red areas:</b><br>Advance order<br>operations",
                    showarrow=False,
                    font=dict(size=10),
                    bgcolor="rgba(255,255,255,0.8)",
                    bordercolor="red",
                    borderwidth=1,
                )
            ],
            hovermode="x unified",
        )
        
        streamlit.plotly_chart(fig, use_container_width=True)
