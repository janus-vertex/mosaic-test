import sys
from pathlib import Path

# Add frontend and backend to Python path
root_dir = Path(__file__).parent
sys.path.extend([str(root_dir / "frontend"), str(root_dir / "backend")])

import streamlit

from frontend.tabs import simulation_tab, result_tab
from frontend.ui_components import StatusCheckUI


def main():
    streamlit.set_page_config(page_title="MOSAIC", page_icon=":robot_face:")

    streamlit.title("Mosaic App")
    streamlit.write("Version 0.8.4")

    status_check_ui = StatusCheckUI()
    status_check_ui.show()

    tab1, tab2 = streamlit.tabs(["Simulation", "Result"])

    with tab1:
        simulation_tab()

    with tab2:
        result_tab()


if __name__ == "__main__":
    main()
