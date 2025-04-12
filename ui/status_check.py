import streamlit

from core.config import TC_BASE_1, TC_BASE_2, SM_BASE_1, SM_BASE_2
from core.requests import MosaicRequest


class StatusCheckUI:
    def __init__(self):
        pass

    def show(self):
        streamlit.write("## Status Check")

        col1, col2 = streamlit.columns(2)
        with col1:
            streamlit.write("Server 1")
            self.check_if_simulation_is_running(TC_base=TC_BASE_1, SM_base=SM_BASE_1)
        with col2:
            streamlit.write("Server 2")
            self.check_if_simulation_is_running(TC_base=TC_BASE_2, SM_base=SM_BASE_2)

    def check_if_simulation_is_running(self, TC_base: str, SM_base: str):
        _, is_simulation_running, _ = (
            MosaicRequest.general_check(TC_base=TC_base, SM_base=SM_base)
        )

        if is_simulation_running:
            streamlit.success("Simulation is running.")
            is_stop_simulation = streamlit.button("Stop Simulation")
            if is_stop_simulation:
                MosaicRequest.stop(TC_base)

        elif not is_simulation_running and is_simulation_running is not None:
            streamlit.success("No simulation is running.")

        else:
            streamlit.warning("Server is unavailable.")
