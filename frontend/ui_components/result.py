from datetime import datetime, timedelta

import plotly.graph_objects as go
import streamlit
from core.simulation_database import SimulationDatabase


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
                lambda x: datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M:%S")
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

        self._show_station_statistics()

        # # Calculate statistics
        # total_entries = station_counts["Count"].sum()
        # avg_entries_per_station = total_entries / len(station_counts)

        # # Display statistics
        # streamlit.subheader("Bin Storage Statistics")
        # col1, col2 = streamlit.columns(2)
        # col1.metric("Total Bins Stored", f"{total_entries}")
        # col2.metric("Average Bins per Station", f"{avg_entries_per_station:.2f}")

        # # Create and display bar chart
        # streamlit.subheader("Bins Stored by Station")
        # chart = streamlit.bar_chart(station_counts.set_index("Station"))

        # # Display the data table
        # streamlit.subheader("Station Storage Data")
        # streamlit.dataframe(station_counts.sort_values("Count", ascending=False))

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

        # Create bar chart
        fig = go.Figure(
            data=[
                go.Bar(
                    x=station_counts["station_code"],
                    y=station_counts["bin_presentation_rate"],
                    text=[
                        f"{rate:.1f}"
                        for rate in station_counts["bin_presentation_rate"]
                    ],
                    textposition="outside",
                )
            ]
        )
        fig.update_layout(
            title="Bin Presentation Rate by Station",
            yaxis_title="Bin Presentation Rate (bins/hour)",
            xaxis=dict(
                title="Station Code",
                type="category",
            ),
        )
        streamlit.plotly_chart(fig)

        