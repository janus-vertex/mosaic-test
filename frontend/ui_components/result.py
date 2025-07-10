from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

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

            # Get the parameters of the chosen simulation run
            simulation_parameters = (
                simulation_database.get_parameters_by_simulation_run(simulation_run_id)
            )
            self.stations = self._parse_stations_from_string(
                simulation_parameters["stations_string"].iloc[0]
            )
            self.advance_order_ranges = self._parse_advance_order_ranges_from_string(
                simulation_parameters["duration_string"].iloc[0],
                log_start_timestamp,
            )

            progress_bar.progress(75)

            streamlit.write("#### Simulation durations")
            self._show_simulation_durations()

            streamlit.write("#### Bin presentation over time")
            self._show_bin_presentation_over_time()

            streamlit.write("#### Bin presentation rate by station")
            is_normal_operation_only = streamlit.toggle(
                "Show normal operation only",
                value=False,
                key="bin_presentation_rate_by_station_toggle",
            )
            self._show_station_statistics(
                is_normal_operation_only=is_normal_operation_only
            )
            progress_bar.progress(83)

            streamlit.write("#### Bin handling rate by skycar")
            is_normal_operation_only = streamlit.toggle(
                "Show normal operation only",
                value=False,
                key="bin_handling_rate_by_skycar_toggle",
            )
            self._show_handling_rate_statistics(
                is_normal_operation_only=is_normal_operation_only
            )
            progress_bar.progress(91)

            progress_bar.progress(100)

        # Clean up connections
        finally:
            if simulation_database is not None:
                simulation_database.close_connection()

            if mongo_service is not None:
                mongo_service.close_connection()

    def _parse_advance_order_ranges_from_string(
        self, duration_string: str, simulation_start_timestamp: float
    ) -> List[Tuple[float, float]]:
        advance_order_ranges = []
        current_time = simulation_start_timestamp

        for segment in duration_string.split(";"):
            if segment.startswith("AO"):
                duration_seconds = float(segment[2:])
                start_timestamp = current_time
                end_timestamp = current_time + duration_seconds
                advance_order_ranges.append((start_timestamp, end_timestamp))
                current_time = end_timestamp
            elif segment.startswith("N"):
                duration_seconds = float(segment[1:])
                current_time += duration_seconds

        return advance_order_ranges

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

    def _show_bin_presentation_over_time(self):
        # Toggle to choose bin size (30 minutes or 1 hour)
        bin_size = streamlit.radio(
            "Select bin size",
            ["30 minutes", "1 hour"],
            index=0,
            key="bin_size_radio",
            horizontal=True,
        )
        bin_size_minutes = 60 if bin_size == "1 hour" else 30

        bin_stored_logs = self.logs[self.logs["action"] == "Bin stored"].copy()

        if bin_stored_logs.empty:
            streamlit.warning("No stored bins in this simulation yet.")
            return

        log_start_timestamp = self.logs["timestamp"].min()
        bin_stored_logs["duration_minutes"] = (
            bin_stored_logs["timestamp"] - log_start_timestamp
        ) / 60
        bin_stored_logs["interval_minutes"] = (
            (bin_stored_logs["duration_minutes"] // bin_size_minutes) * bin_size_minutes
        ).astype(int)

        # Group by interval and station_code, then count occurrences
        interval_station_counts = (
            bin_stored_logs.groupby(["interval_minutes", "station_code"])
            .size()
            .reset_index(name="count")
        )

        # Get all unique intervals and stations for complete data
        max_interval = bin_stored_logs["interval_minutes"].max()
        all_intervals = list(
            range(
                0,
                int(max_interval) + bin_size_minutes,
                bin_size_minutes,
            )
        )
        all_stations = sorted([station.code for station in self.stations])

        complete_data = []
        for interval in all_intervals:
            for station in all_stations:
                matching_rows = interval_station_counts[
                    (interval_station_counts["interval_minutes"] == interval)
                    & (interval_station_counts["station_code"] == station)
                ]
                count_value = (
                    matching_rows["count"].iloc[0] if not matching_rows.empty else 0
                )
                complete_data.append(
                    {
                        "interval_minutes": interval,
                        "station_code": station,
                        "count": count_value,
                    }
                )

        complete_df = pandas.DataFrame(complete_data)

        # Create stacked bar chart
        fig = go.Figure()

        # Convert all intervals to hours for consistent x-axis
        all_intervals_hours = [interval / 60 for interval in all_intervals]

        # Add a bar trace for each station
        for station in all_stations:
            station_data = complete_df[complete_df["station_code"] == station]
            # Sort by interval to ensure proper order
            station_data = station_data.sort_values("interval_minutes")

            # Convert minutes to hours for x-axis display
            x_values = (station_data["interval_minutes"] + bin_size_minutes / 2) / 60
            y_values = station_data["count"]

            # Only show text labels for non-zero values to avoid clutter
            text_values = [str(count) if count > 0 else "" for count in y_values]

            fig.add_trace(
                go.Bar(
                    name=f"Station {station}",
                    x=x_values,
                    y=y_values,
                    text=text_values,
                    textposition="auto",
                    width=bin_size_minutes / 60 * 0.9,
                )
            )

        # Add advance order period highlights
        log_start_timestamp = self.logs["timestamp"].min()
        y_max = complete_df.groupby("interval_minutes")["count"].sum().max()
        if y_max > 0:
            for start_ts, end_ts in self.advance_order_ranges:
                # Convert timestamps to duration from start in hours
                start_hours = (start_ts - log_start_timestamp) / 3600
                end_hours = (end_ts - log_start_timestamp) / 3600
                fig.add_vrect(
                    x0=start_hours,
                    x1=end_hours,
                    fillcolor="red",
                    opacity=0.2,
                    layer="below",
                    line_width=0,
                )

        fig.update_layout(
            xaxis_title="Duration from start (hours)",
            yaxis_title="Bin Count",
            barmode="stack",
            xaxis=dict(
                tickmode="linear",
                tick0=all_intervals_hours[0],
                dtick=bin_size_minutes / 60,
                range=[
                    all_intervals_hours[0] - bin_size_minutes * 0.2 / 60,
                    all_intervals_hours[-1] + bin_size_minutes * 1.2 / 60,
                ],
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
            ),
            hovermode="x unified",
        )

        streamlit.plotly_chart(fig, use_container_width=True)
