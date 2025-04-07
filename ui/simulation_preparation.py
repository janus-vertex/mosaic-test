import math
from typing import List

import streamlit

from core.parameters import Parameters
from input_creation import (
    InputBuffer,
    InputJobs,
    InputSkyCarSetup,
    InputSMObstacles,
    InputTCObstacles,
    InputZonesAndStations,
    InputDelay,
)
from ui.grid_designer import GridDesignerUI
from ui.simulation_input import SimulationInputUI


class SimulationPreparationUI:
    def __init__(
        self, grid_designer_ui: GridDesignerUI, simulation_input_ui: SimulationInputUI
    ):
        self.grid_designer_ui = grid_designer_ui
        self.simulation_input_ui = simulation_input_ui

    def show(self) -> bool:
        streamlit.write("## Simulation Preparation")

        # Create input objects
        input_zones_and_stations = InputZonesAndStations(
            grid_designer_ui=self.grid_designer_ui
        )
        input_sm_obstacles = InputSMObstacles(grid_designer_ui=self.grid_designer_ui)
        input_buffer = InputBuffer(buffer_ratio=self.grid_designer_ui.buffer_ratio)
        input_skycar_setup = InputSkyCarSetup(
            number_of_skycars=self.simulation_input_ui.number_of_skycars,
            model=Parameters.ZONE_NAME,
        )
        input_tc_obstacles = InputTCObstacles(grid_designer_ui=self.grid_designer_ui)
        input_delay = InputDelay(
            simulation_input_ui=self.simulation_input_ui,
            input_zones_and_stations=input_zones_and_stations,
        )
        input_jobs_list = self._create_input_jobs_list(
            input_zones_and_stations=input_zones_and_stations
        )

        # Option to show request files
        is_show_files = streamlit.checkbox("Show request files")
        if is_show_files:
            with streamlit.expander("reset-2.json: Zones and Stations"):
                json_data = input_zones_and_stations.to_json()
                self._show_individual_json_file(
                    json_data=json_data, file_name="reset-2.json"
                )

            with streamlit.expander("reset-3.json: SM Obstacles"):
                json_data = input_sm_obstacles.to_json()
                self._show_individual_json_file(
                    json_data=json_data, file_name="reset-3.json"
                )

            with streamlit.expander("reset-4.json: Buffer"):
                json_data = input_buffer.to_json()
                self._show_individual_json_file(
                    json_data=json_data, file_name="reset-4.json"
                )

            with streamlit.expander("reset-5.json: Skycar Setup"):
                json_data = input_skycar_setup.to_json()
                self._show_individual_json_file(
                    json_data=json_data, file_name="reset-5.json"
                )

            with streamlit.expander("reset-6.json: TC Obstacles"):
                json_data = input_tc_obstacles.to_json()
                self._show_individual_json_file(
                    json_data=json_data, file_name="reset-6.json"
                )

            with streamlit.expander("reset-delay.json: Delay"):
                json_data = input_delay.to_json()
                self._show_individual_json_file(
                    json_data=json_data, file_name="reset-delay.json"
                )

            for input_jobs in input_jobs_list:
                with streamlit.expander(
                    f"reset-job-{input_jobs.minLayer}.json: Job Parameters"
                ):
                    json_data = input_jobs.to_json()
                    self._show_individual_json_file(
                        json_data=json_data,
                        file_name=f"reset-job-{input_jobs.minLayer}.json",
                    )

        server_number = streamlit.selectbox(
            "Choose a server to run the simulation on.",
            [1, 2],
            index=None,
            placeholder="Select server...",
        )
        if server_number is None:
            return False

        self.input_zones_and_stations = input_zones_and_stations
        self.input_sm_obstacles = input_sm_obstacles
        self.input_buffer = input_buffer
        self.input_skycar_setup = input_skycar_setup
        self.input_tc_obstacles = input_tc_obstacles
        self.input_delay = input_delay
        self.input_jobs_list = input_jobs_list
        self.server_number = server_number

        return True

    def _show_individual_json_file(self, json_data: str, file_name: str):
        streamlit.download_button(
            label="Download",
            data=json_data,
            file_name=file_name,
            mime="application/json",
            type="primary",
        )
        streamlit.json(json_data)

    def _create_input_jobs_list(
        self, input_zones_and_stations: InputZonesAndStations
    ) -> List[InputJobs]:
        return [
            InputJobs(
                input_zones_and_stations=input_zones_and_stations,
                min_layer=i,
                max_layer=i,
                quantity=math.ceil(
                    len(input_zones_and_stations.stations)
                    * self.simulation_input_ui.goods_in_throughput
                    * self.simulation_input_ui.simulation_duration
                    * self.simulation_input_ui.order_line_distribution_probabilities[
                        i - 1
                    ]
                ),
            )
            for i in range(1, self.grid_designer_ui.z_size + 1)
        ]
