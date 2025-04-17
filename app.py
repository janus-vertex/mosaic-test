import sys
from pathlib import Path

# Add frontend and backend to Python path
root_dir = Path(__file__).parent
sys.path.extend([str(root_dir / "frontend"), str(root_dir / "backend")])

import streamlit

from frontend.core.simulator import Simulator
from frontend.ui_components import (
    GridDesignerUI,
    SimulationInputUI,
    SimulationPreparationUI,
    StatusCheckUI,
)


def main():
    streamlit.title("Mosaic App")

    status_check_ui = StatusCheckUI()
    status_check_ui.show()

    grid_designer_ui = GridDesignerUI()
    is_grid_designer_ui_success = grid_designer_ui.show()

    simulation_input_ui = SimulationInputUI(grid_designer_ui=grid_designer_ui)
    is_simulation_input_ui_success = simulation_input_ui.show()

    if not is_grid_designer_ui_success or not is_simulation_input_ui_success:
        return

    simulation_preparation_ui = SimulationPreparationUI(
        grid_designer_ui=grid_designer_ui, simulation_input_ui=simulation_input_ui
    )
    is_simulation_preparation_ui_success = simulation_preparation_ui.show()

    if not is_simulation_preparation_ui_success:
        return

    simulator = Simulator(simulation_preparation_ui=simulation_preparation_ui)

    is_start_simulation = streamlit.button("Start Simulation", type="primary")

    if is_start_simulation:
        simulator.run()


if __name__ == "__main__":
    main()
