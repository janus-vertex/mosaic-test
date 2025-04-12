import json

import requests
import streamlit

from core.config import SM_BASE_1, SM_BASE_2, TC_BASE_1, TC_BASE_2
from core.requests import MosaicRequest
from ui.simulation_preparation import SimulationPreparationUI


class Simulator:
    def __init__(self, simulation_preparation_ui: SimulationPreparationUI):
        self.simulation_preparation_ui = simulation_preparation_ui
        self._set_server()

    def run(self):
        _, is_simulation_running, _ = (
            MosaicRequest.general_check(TC_base=self.TC_BASE, SM_base=self.SM_BASE)
        )
        if is_simulation_running:
            streamlit.warning(
                "A simulation is running. Please stop it before running another one by "
                + "pressing the stop button at the top of the page.",
                icon="⚠️",
            )
            return

        steps = [
            ("Reset Layout", self._reset_layout),
            ("Initialise Setup", self._initialise_setup),
            ("Configure SM Obstacles", self._configure_SM_obstacles),
            ("Configure Layout", self._configure_layout),
            ("Configure TC Obstacles", self._configure_TC_obstacles),
            ("Configure Skycar Setup", self._configure_skycar_setup),
            ("Start Cube", self._start_cube),
            ("Set Time Delay", self._set_delay),
            ("Send Jobs", self._send_list_of_jobs),
        ]

        progress_bar = streamlit.progress(0)
        status_text = streamlit.empty()

        for i, (step_name, step_func) in enumerate(steps):
            status_text.text(f"Running: {step_name}")
            _ = step_func()
            progress_bar.progress((i + 1) / len(steps))

        status_text.text("Simulation setup complete!")

    def stop(self) -> requests.Response | None:
        try:
            response = MosaicRequest.send_request(
                url=f"{self.TC_BASE}/operation/cyclestop",
                data={
                    "status": "Enabled",
                    "reason": "Matrix simulation has stopped the simulation.",
                },
            )
            streamlit.success("Simulation stopped successfully.", icon="✅")
            return response
        except requests.exceptions.RequestException as _:
            streamlit.warning(
                "Failed to stop simulation, or there is no simulation to be stopped.",
                icon="⚠️",
            )
            return None

    def _set_server(self):
        if self.simulation_preparation_ui.server_number == 1:
            self.SM_BASE = SM_BASE_1
            self.TC_BASE = TC_BASE_1
        elif self.simulation_preparation_ui.server_number == 2:
            self.SM_BASE = SM_BASE_2
            self.TC_BASE = TC_BASE_2

    def _reset_layout(self) -> requests.Response:
        response = MosaicRequest.send_request(
            url=f"{self.SM_BASE}/v3/initialize/reset",
        )
        return response

    def _initialise_setup(self) -> requests.Response:
        response = MosaicRequest.send_request(
            url=f"{self.SM_BASE}/v3/initialize",
            data=self.simulation_preparation_ui.input_zones_and_stations.to_json(
                type="dict"
            ),
        )
        return response

    def _configure_SM_obstacles(self) -> requests.Response:
        response = MosaicRequest.send_request(
            url=f"{self.SM_BASE}/v3/obstacles",
            data=self.simulation_preparation_ui.input_sm_obstacles.to_json(type="dict"),
        )
        return response

    def _configure_layout(self) -> requests.Response:
        response = MosaicRequest.send_request(
            url=f"{self.SM_BASE}/v3/initialize/storage",
            data=self.simulation_preparation_ui.input_buffer.to_json(type="dict"),
        )
        return response

    def _configure_skycar_setup(self) -> requests.Response:
        response = MosaicRequest.send_request(
            url=f"{self.TC_BASE}/simulation/seed-skycars",
            data=self.simulation_preparation_ui.input_skycar_setup.to_json(type="dict"),
        )
        return response

    def _configure_TC_obstacles(self) -> requests.Response:
        response = MosaicRequest.send_request(
            url=f"{self.TC_BASE}/wcs/obstacle",
            data=self.simulation_preparation_ui.input_tc_obstacles.to_json(type="dict"),
        )
        return response

    def _start_cube(self) -> requests.Response:
        response = MosaicRequest.send_request(
            url=f"{self.TC_BASE}/operation/cube?start=true&bypass=true",
        )
        return response

    def _set_delay(self) -> requests.Response:
        response = MosaicRequest.send_request(
            url=f"{self.SM_BASE}/v3/settings/auto-store",
            method="PUT",
            data=self.simulation_preparation_ui.input_delay.to_json(type="dict"),
        )
        return response

    def _send_list_of_jobs(self) -> requests.Response:
        for input_jobs in self.simulation_preparation_ui.input_jobs_list:
            _ = MosaicRequest.send_request(
                url=f"{self.SM_BASE}/v3/dry-runs",
                data=input_jobs.to_json(type="dict"),
            )
