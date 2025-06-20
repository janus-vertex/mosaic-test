import math

import streamlit

from core.pareto import ParetoCalculator
from ui_components.grid_designer import GridDesignerUI
import plotly.graph_objects as go
import pandas


class SimulationInputUI:
    """
    The UI for simulation input.
    """

    def __init__(self, grid_designer_ui: GridDesignerUI):
        self.grid_designer_ui = grid_designer_ui

    def show(self):
        streamlit.write("## Simulation Input")

        streamlit.write("#### General settings")
        is_success = True

        simulation_name = streamlit.text_input(
            "Simulation name (default name is given if left blank)", value="default-sim"
        )
        # Validate simulation name - only alphanumeric characters, dashes, and underscores allowed
        if simulation_name == "" or not all(
            c.isalnum() or c in ["-", "_"] for c in simulation_name
        ):
            streamlit.error(
                "Simulation name must contain only alphanumeric characters, dashes, or underscores.",
                icon="❌",
            )
            is_success = False

        streamlit.text(
            "Simulation duration (add more rows to include different operation types)"
        )
        duration_df = pandas.DataFrame(
            {"duration_in_minutes": [30], "type": ["Normal"]}
        )
        durations = streamlit.data_editor(
            duration_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "duration_in_minutes": streamlit.column_config.NumberColumn(
                    "Duration (minutes; multiple of 10)",
                    min_value=10,
                    max_value=1440,
                    step=10,
                    required=True,
                    width="medium",
                ),
                "type": streamlit.column_config.SelectboxColumn(
                    "Operation Type",
                    options=["Advance Order", "Normal"],
                    required=True,
                    width="medium",
                ),
            },
            column_order=["duration_in_minutes", "type"],
        )
        if durations.empty:
            streamlit.error("Simulation duration must be provided.", icon="❌")
            is_success = False

        self._display_durations(durations)
        self._store_durations(durations)

        streamlit.write("#### Peak number of bins per order")
        col1, col2 = streamlit.columns(2)
        inbound_bins_per_order = col1.number_input(
            "Inbound bins per order", min_value=1, value=20, max_value=500
        )
        outbound_bins_per_order = col2.number_input(
            "Outbound bins per order", min_value=1, value=20, max_value=500
        )

        streamlit.write("#### Peak number of orders per hour")
        col1, col2 = streamlit.columns(2)
        inbound_orders_per_hour = col1.number_input(
            "Inbound orders per hour", min_value=1, value=10, max_value=100
        )
        outbound_orders_per_hour = col2.number_input(
            "Outbound orders per hour", min_value=1, value=10, max_value=100
        )

        inbound_throughput = inbound_orders_per_hour * inbound_bins_per_order
        outbound_throughput = outbound_orders_per_hour * outbound_bins_per_order
        recommended_number_of_skycars = self._recommend_number_of_skycars(
            total_throughput=inbound_throughput + outbound_throughput
        )
        streamlit.write("#### Number of skycars")
        col1, col2 = streamlit.columns(2)
        number_of_skycars = col1.number_input(
            "Number of skycars",
            min_value=1,
            max_value=100,
            value=10,
        )
        col2.metric(
            "✅ Recommended number of skycars",
            recommended_number_of_skycars,
            border=True,
        )

        streamlit.write("#### Operator handling times")
        col1, col2 = streamlit.columns(2)
        inbound_time = col1.number_input(
            "Inbound handling time (s)", min_value=1, value=20
        )
        outbound_time = col2.number_input(
            "Outbound handling time (s)", min_value=1, value=20
        )

        streamlit.write("#### Bin distribution")
        with streamlit.expander("More information"):
            streamlit.write(
                """ 
                The bin distribution is based on generalised truncated Pareto 
                distribution. Input `p` and `q`, such that `q%` of SKUs contribute 
                to `p%` of the job volume (note the order of `p` and `q`). This is also 
                equivalent to `p%` of bins contribute to top `q%` of the layers 
                in the grid.

                For example, the standard 80/20 rule implies that 20% of the SKUs
                contribute to 80% of the job volume. Equivalently, 80% of the bins
                contribute to the top 20% of the layers in the grid. In this example,
                `p = 80` and `q = 20`.
                """
            )

        col1, col2 = streamlit.columns(2)
        pareto_p = (
            col1.number_input("p (%)", min_value=0, max_value=100, value=80) / 100
        )
        pareto_q = (
            col2.number_input("q (%)", min_value=0, max_value=100, value=20) / 100
        )

        self._show_bin_distribution_plot(pareto_p, pareto_q)

        # Assign values for later use
        self.simulation_name = simulation_name
        self.inbound_bins_per_order = inbound_bins_per_order
        self.outbound_bins_per_order = outbound_bins_per_order
        self.inbound_orders_per_hour = inbound_orders_per_hour
        self.outbound_orders_per_hour = outbound_orders_per_hour
        self.inbound_time = inbound_time
        self.outbound_time = outbound_time
        self.number_of_skycars = number_of_skycars
        self.pareto_p = pareto_p
        self.pareto_q = pareto_q

        streamlit.divider()

        return is_success

    def _recommend_number_of_skycars(self, total_throughput: int):
        """
        Recommend the number of skycars based on the inbound and outbound throughputs. One
        robot can roughly handle 25 bins per hour.
        """
        return math.ceil(total_throughput / 25)

    def _show_bin_distribution_plot(self, pareto_p: float, pareto_q: float):
        z_size = self.grid_designer_ui.z_size
        if z_size is None:
            return

        pareto = ParetoCalculator(min_x=1, max_x=z_size)
        x0, alpha = pareto.get_alpha(p=pareto_p, q=pareto_q)

        probabilities_percent = [
            pareto.probability_of_layer(layer=layer, alpha=alpha) * 100
            for layer in range(1, z_size + 1)
        ]
        top_x0_sum = sum(probabilities_percent[: int(x0)])
        streamlit.info(
            f"{top_x0_sum:.1f}% of the bins go into the top {int(x0)} "
            + f"({x0/z_size*100:.1f}%) layer(s).",
        )

        fig = go.Figure(
            data=go.Bar(
                x=list(range(1, z_size + 1)),
                y=probabilities_percent,
                text=[f"{p:.2f}" for p in probabilities_percent],
                textposition="outside",
            )
        )

        fig.update_layout(
            title="Bin Distribution by Position of Layer",
            xaxis_title="Position of Layer",
            yaxis_title="Probability of layer (%)",
            showlegend=False,
        )

        # Calculate sum of top int(x0) probabilities_percent
        fig.update_traces(
            marker_pattern_shape=["\\"] * int(x0) + [""] * (z_size - int(x0)),
            marker_pattern_solidity=0.8,
        )

        streamlit.plotly_chart(fig)

        self.pareto_probabilities = [i / 100 for i in probabilities_percent]

    def _display_durations(self, durations: pandas.DataFrame):

        if durations.empty:
            return

        fig = go.Figure()

        max_time = durations["duration_in_minutes"].sum()
        # Add base line for full duration
        fig.add_trace(
            go.Scatter(
                x=[0, max_time],
                y=[1, 1],
                mode="lines",
                line=dict(width=8, color="#0068c9"),
                name="Normal",
            )
        )
        # Add red segments for each advance order
        for i in range(len(durations)):
            if durations.iloc[i]["type"] == "Advance Order":
                start = durations.iloc[:i]["duration_in_minutes"].sum()
                end = durations.iloc[: i + 1]["duration_in_minutes"].sum()

                fig.add_trace(
                    go.Scatter(
                        x=[start, end],
                        y=[1, 1],
                        mode="lines",
                        line=dict(width=8, color="#ffabab"),
                        name="",
                    )
                )

        # Add markers for min and max points
        fig.add_trace(
            go.Scatter(
                x=[0, max_time],
                y=[1, 1],
                mode="markers",
                marker=dict(size=20, color="#83c9ff"),
                showlegend=False,
                name="",
            )
        )

        # Update layout
        hours = int(max_time // 60)
        minutes = int(max_time % 60)

        hours_text = f"{hours}h" if hours > 0 else ""
        minutes_text = f"{minutes}m" if minutes > 0 else ""
        duration_text = f"Total: {hours_text} {minutes_text}"

        fig.update_layout(
            title="Simulation Operation Time Range",
            showlegend=False,
            annotations=[
                dict(
                    text=duration_text,
                    x=max_time,
                    y=2.5,
                    xref="x",
                    yref="paper",
                    showarrow=False,
                    font=dict(size=14),
                )
            ],
            yaxis=dict(
                showticklabels=False, showgrid=False, zeroline=False, range=[0.9, 1.1]
            ),
            xaxis=dict(title="Minutes", zeroline=True),
            height=200,
        )

        streamlit.plotly_chart(fig)

    def _store_durations(self, durations: pandas.DataFrame):
        operation_ranges = []
        current_type = None
        current_duration = 0
        for _, row in durations.iterrows():
            duration = row["duration_in_minutes"]
            op_type = row["type"]

            if current_type is None:
                current_type = op_type
                current_duration = duration
            elif current_type == op_type:
                current_duration += duration
            else:
                # Convert minutes to seconds and create range string
                prefix = "AO" if current_type == "Advance Order" else "N"
                operation_ranges.append(f"{prefix}{int(current_duration * 60)}")
                current_type = op_type
                current_duration = duration

        # Add the last range
        if current_type is not None:
            prefix = "AO" if current_type == "Advance Order" else "N"
            operation_ranges.append(f"{prefix}{int(current_duration * 60)}")

        self.duration_string = ";".join(operation_ranges)

        streamlit.write(self.duration_string)
