import math

import streamlit

from core.pareto import ParetoCalculator
from ui.grid_designer import GridDesignerUI
import plotly.graph_objects as go


class SimulationInputUI:
    """
    The UI for simulation input.
    """

    def __init__(self, grid_designer_ui: GridDesignerUI):
        self.grid_designer_ui = grid_designer_ui

    def show(self):
        streamlit.write("## Simulation Input")

        streamlit.write("#### Peak throughput per station")
        col1, col2 = streamlit.columns(2)
        pick_throughput = col1.number_input(
            "Pick throughput (bins/h)", min_value=1, value=1000
        )
        goods_in_throughput = col2.number_input(
            "Goods-in throughput (bins/h)", min_value=1, value=100
        )

        recommended_number_of_skycars = self._recommend_number_of_skycars(
            total_throughput=pick_throughput + goods_in_throughput
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
        pick_time = col1.number_input("Pick handling time (s)", min_value=1, value=20)
        goods_in_time = col2.number_input(
            "Goods-in handling time (s)", min_value=1, value=20
        )

        streamlit.write("#### Simulation duration")
        simulation_duration = streamlit.selectbox(
            "Approximate simulation duration",
            options=[
                "10 minutes",
                "30 minutes",
                "1 hour",
                "2 hours",
                "4 hours",
                "8 hours",
            ],
        )
        duration_mapping = {
            "10 minutes": 1 / 6,
            "30 minutes": 1 / 2,
            "1 hour": 1,
            "2 hours": 2,
            "4 hours": 4,
            "8 hours": 8,
        }
        simulation_duration = duration_mapping[simulation_duration]

        streamlit.write("#### Order line distribution")
        with streamlit.expander("More information"):
            streamlit.write(
                """ 
                The order line distribution is based on generalised truncated Pareto 
                distribution. Input `p` and `q`, such that `q%` of SKUs contribute 
                to `p%` of the job volume (note the order of `p` and `q`). This is also 
                equivalent to `p%` of order lines contribute to top `q%` of the layers 
                in the grid.

                For example, the standard 80/20 rule implies that 20% of the SKUs
                contribute to 80% of the jobvolume. Equivalently, 80% of the order lines
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

        self._show_order_line_distribution_plot(pareto_p, pareto_q)

        # Assign values for later use
        self.pick_throughput = pick_throughput
        self.goods_in_throughput = goods_in_throughput
        self.pick_time = pick_time
        self.goods_in_time = goods_in_time
        self.number_of_skycars = number_of_skycars
        self.simulation_duration = simulation_duration

        streamlit.divider()

        return True

    def _recommend_number_of_skycars(self, total_throughput: int):
        """
        Recommend the number of skycars based on the pick and goods-in throughputs. One
        robot can roughly handle 25 bins per hour.
        """
        return math.ceil(total_throughput / 25)

    def _show_order_line_distribution_plot(self, pareto_p: float, pareto_q: float):
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
            f"{top_x0_sum:.1f}% of the order lines go into the top {int(x0)} layer(s).",
        )

        # xq = pareto_q * z_size + 1
        # theoretical_minimum_p = pareto.cdf(xq, alpha=0.001)
        # theoretical_maximum_q = (pareto.inverse_cdf(pareto_p, alpha=0.001) - 1) / z_size

        # streamlit.info(f"Theoretical minimum p: {theoretical_minimum_p}")
        # streamlit.info(f"Theoretical maximum q: {theoretical_maximum_q}")

        fig = go.Figure(
            data=go.Bar(
                x=list(range(1, z_size + 1)),
                y=probabilities_percent,
                text=[f"{p:.2f}" for p in probabilities_percent],
                textposition="outside",
            )
        )

        fig.update_layout(
            title="Order Line Distribution by Position of Layer",
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

        self.order_line_distribution_probabilities = [
            i / 100 for i in probabilities_percent
        ]
