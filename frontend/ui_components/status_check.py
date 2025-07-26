import streamlit
from core.config import (
    SIMULATION_BASE_1,
    SIMULATION_BASE_2,
    SM_BASE_1,
    SM_BASE_2,
    TC_BASE_1,
    TC_BASE_2,
    DASHBOARD_1,
    DASHBOARD_2,
)

from frontend.core.simulation_requests import MosaicRequest


class StatusCheckUI:
    """
    Status check UI component
    """
    def __init__(self):
        pass

    def show(self):
        """
        Show the status of Server 1 and Server 2.
        """
        streamlit.write("## Status Check")

        col1, col2 = streamlit.columns(2)
        with col1:
            streamlit.write("Server 1")
            streamlit.link_button("Dashboard 1", DASHBOARD_1)
            self.check_if_simulation_is_running(
                TC_base=TC_BASE_1, SM_base=SM_BASE_1, simulation_base=SIMULATION_BASE_1
            )
        with col2:
            streamlit.write("Server 2")
            streamlit.link_button("Dashboard 2", DASHBOARD_2)
            self.check_if_simulation_is_running(
                TC_base=TC_BASE_2, SM_base=SM_BASE_2, simulation_base=SIMULATION_BASE_2
            )

    def check_if_simulation_is_running(
        self, TC_base: str, SM_base: str, simulation_base: str
    ):
        """
        Check if simulation is running on the server.

        Parameters
        ----------
        TC_base : str
            TC base URL
        SM_base : str
            SM base URL
        simulation_base : str
            Simulation base URL
        """
        is_healthy, is_tc_running, is_simulation_completed, simulation_name = (
            MosaicRequest.general_check(
                TC_base=TC_base, SM_base=SM_base, simulation_base=simulation_base
            )
        )

        if not is_healthy:
            streamlit.warning("Server is unavailable.")

        # Simulation can be running or completed even though TC is active.
        elif is_tc_running:
            if is_simulation_completed:
                streamlit.success(
                    f"Simulation {simulation_name} completed successfully!"
                )
            else:
                streamlit.success(f"Simulation {simulation_name} is running.")
            is_stop_simulation = streamlit.button(
                "Stop Simulation", key=f"{TC_base} stop button"
            )

            # Stop simulation if button is clicked.
            if is_stop_simulation:
                MosaicRequest.stop(TC_base=TC_base, simulation_base=simulation_base)

        # If TC is not running, it means no simulation exists in the system.
        elif is_tc_running is False:
            streamlit.success("No simulation is running.")

        # Other factors are considered as server is unavailable.
        else:
            streamlit.warning("Server is unavailable.")
