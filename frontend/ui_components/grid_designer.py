import math
import re
from pathlib import Path
from typing import List

import numpy
import pandas
import plotly.graph_objects as go
import streamlit

EXCEL_OPTIONS = [0, 1, 2, 3]
MAX_SIZE = 50


class GridDesignerUI:
    """
    The UI for grid designer.

    Attributes
    ----------
    buffer_ratio : float
        The buffer ratio of the grid, i.e. how many empty bins are there in the grid.
        Note that empty bins are not the same as empty grid spaces. Value is between 0
        and 1.
    z_size : int
        The height of the grid in number of bins.
    grid_data : pandas.DataFrame
        The grid data previously imported as an Excel file..
    stations : List[str]
        The stations string from the grid data. Example inputs are "P1I", "P2DI", "P3PO".
    number_of_bins : int
        The number of bins in the grid.
    has_inbound : bool
        True if the grid has inbound stations, False otherwise.
    has_outbound : bool
        True if the grid has outbound stations, False otherwise.
    station_code_groups : List[List[int]]
        The list of groups of station indices. A station group means that the stations
        share the same order.
    desired_skycar_directions : pandas.DataFrame
        The desired skycar directions input to be processed as skycar direction
        constraints.
    """

    def __init__(self):
        self.buffer_ratio: float = None
        self.z_size: int = None
        self.grid_data: pandas.DataFrame = None
        self.stations: List[str] = None
        self.number_of_bins: int = None
        self.has_inbound: bool = True
        self.has_outbound: bool = True
        self.station_code_groups = None
        self.desired_skycar_directions = None

    def show(self) -> bool:
        """
        Display the grid designer UI.

        Returns
        -------
        bool
            True if the grid designer UI can be displayed successfully, False otherwise.
        """
        streamlit.write("## Grid Design")
        self._show_buttons_and_instructions()

        grid_excel_file = streamlit.file_uploader("Upload grid excel.")

        col1, col2 = streamlit.columns(2)
        number_of_bins = col1.number_input(
            "Number of bins expected", min_value=1, value=1000, step=1
        )
        self.number_of_bins = number_of_bins
        buffer_percentage = col2.number_input(
            "Buffer percentage expected", min_value=0, max_value=100, value=15, step=1
        )

        if grid_excel_file is None:
            streamlit.warning("No grid file uploaded.", icon="⚠️")

        else:
            grid_data = pandas.read_excel(
                grid_excel_file, header=0, index_col=0, dtype=str
            )

            # Drop first row and first column, following the template given
            grid_data = grid_data.dropna(how="all", axis=0)
            grid_data = grid_data.dropna(how="all", axis=1)

            # Convert grid data to numeric, coercing non-numeric values to NaN, then get
            # the maximum value, ignoring NaN
            numeric_grid = pandas.to_numeric(grid_data.values.ravel(), errors="coerce")
            self.z_size = int(numeric_grid[~numpy.isnan(numeric_grid)].max())
            self.grid_data = grid_data

            # Check whether the stations are valid.
            is_success = self._check_station_validity()
            if not is_success:
                return False

            # Add lines to indicate desired skycar directions
            self._get_desired_skycar_directions()

            # Display the grid.
            self._display_grid()

            is_success = self._choose_linked_stations()
            if not is_success:
                return False

        col1, col2, col3 = streamlit.columns(3)
        gross_number_of_spaces_expected = math.floor(
            number_of_bins / ((100 - buffer_percentage) / 100)
        )
        col1.metric(
            "Gross number of spaces expected",
            value=gross_number_of_spaces_expected,
        )
        if grid_excel_file is None:
            gross_number_of_spaces_from_grid = "N/A"
            delta_gross_number = None
            buffer_percentage_from_grid = "N/A"
            delta_buffer_percentage = None
        else:
            numeric_grid = pandas.to_numeric(
                self.grid_data.values.ravel(), errors="coerce"
            )
            gross_number_of_spaces_from_grid = int(
                numeric_grid[~numpy.isnan(numeric_grid)].sum()
            )
            delta_gross_number = (
                gross_number_of_spaces_from_grid - gross_number_of_spaces_expected
            )

            buffer_ratio_from_grid = (
                gross_number_of_spaces_from_grid - number_of_bins
            ) / gross_number_of_spaces_from_grid
            buffer_percentage_from_grid = f"{buffer_ratio_from_grid * 100:.1f}%"
            delta_buffer_percentage = (
                f"{buffer_ratio_from_grid * 100 - buffer_percentage:.1f}%"
            )

            self.buffer_ratio = buffer_ratio_from_grid

        col2.metric(
            "Gross number of spaces from grid",
            value=gross_number_of_spaces_from_grid,
            delta=delta_gross_number,
            delta_color="off",
        )
        col3.metric(
            "🟢 Buffer percentage from grid",
            value=buffer_percentage_from_grid,
            delta=delta_buffer_percentage,
            delta_color="off",
            # border=True,
        )

        if self.buffer_ratio is not None and self.buffer_ratio < 0:
            streamlit.error(
                "Number of bins expected is more than the spaces available in the grid. "
                + "Please reduce the number of bins expected or allow more spaces in "
                + "the grid.",
                icon="❌",
            )
            return False

        streamlit.divider()

        if grid_excel_file is None:
            return False

        return True

    def _show_buttons_and_instructions(self):
        """
        Show the buttons and instructions for the grid designer.
        """
        streamlit.write(
            "Upload a grid excel file for simulation. To get started, click below for "
            + "template or example, or refer to the instructions."
        )

        # Update file paths to use absolute paths from project root
        files_dir = Path(__file__).parents[1] / "files"
        template_path = files_dir / "template.xlsx"
        example_path = files_dir / "example.xlsx"

        # Download template and example files.
        streamlit.download_button(
            "Download template",
            file_name="template.xlsx",
            data=open(template_path, "rb").read(),
            type="primary",
        )
        streamlit.download_button(
            "Download example",
            file_name="example.xlsx",
            data=open(example_path, "rb").read(),
            type="primary",
        )

        with streamlit.expander("Instructions: general"):
            streamlit.write(
                """
                To get started, use the template and refer to the example given.
                
                The first row and column of the grid excel file are the indices of the grid. 
                The grid data starts from the second row and second column.

                Formatting (e.g. cell colour, font colour, cell size, cell borders) does 
                not matter, as long as the inputs are valid. You may use your own 
                preferred formatting for the ease of designing the grid.
                """
            )

        with streamlit.expander("Instructions: valid inputs"):
            streamlit.write(
                """
                Valid inputs are:
                - Free stack: Any numeric value (e.g. 1, 2, 3)
                - Stations: "P + station number + optional D/P + ends withO/I" (e.g. 
                P1I, P21DI, P2PI, P3DO, P3PO) 
                - Buffers: "B" 
                - Others: Any other characters not defined above
                - Unavailable stack: Left empty

                **1. Free stack** 

                Free stacks are the cells that bins can be placed into. The numeric 
                value given is the depth of the stack in bins.

                **2. Stations**

                Stations are the cells that bins can be picked from and dropped into. 
                They are cells that start with "P", and must follow the pattern 
                "P + station number + optional D/P + O/I". The optional "D" or "P" 
                indicates the station port is for drop or pick, while the last mandatory 
                character "I" or "O" indicates the station is for inbound or outbound 
                operation.

                If the station is for both pick and drop, the optional D/P is not 
                required. For example, "P1O" and "P100I".

                If the station port is for pick only, then the character P is required. For 
                example, "P2PI", "P30PO". Likewise, if the station port is for drop only, then 
                the character D is required. For example, "P2DI", "P50DO". 

                Note that the pick and drop ports must come in pair. In other words, 
                if "P1PI" is created, then there must be "P1DI", and vice versa.  

                Each station must be assigned inbound "I" or outbound "O" as the last 
                character. If the station has two ports, then both ports must have the 
                same inbound or outbound character. For example, "P3DI" and "P3PI" are 
                valid, but "P3DI" and "P3PO" are invalid.

                No two stations can share the same station number, unless they are 
                separate drop and pick ports. For example, if "P1I" exists, then "P1DI" 
                or "P1PI" is invalid, and vice versa. 

                **3. Buffers**

                Buffers are the cells that bins cannot be placed into, but skycars can 
                travel across. They are denoted as "B".

                **4. Others**

                All other characters that are not defined above are considered as 
                others. They are treated as unavailable stacks in the simulation. You may 
                use this to represent chargers, obstacles, etc.

                **5. Unavailable stack**

                Unavailable stacks are the cells that are not used in the grid. They 
                should be left empty.
                """
            )

    def _check_station_validity(self) -> bool:
        """
        Check that the stations are valid.

        Returns
        -------
        bool
            True if the stations are valid, False otherwise.
        """
        # Find positions of all stations (cells starting with 'P')
        station_mask = self.grid_data.map(lambda x: str(x).startswith("P")).to_numpy()
        station_positions = numpy.argwhere(station_mask)
        stations = self.grid_data.values[
            station_positions[:, 0], station_positions[:, 1]
        ].tolist()

        if not stations:
            streamlit.error("No stations found in grid.", icon="❌")
            return False

        # Check for duplicates
        if len(stations) != len(set(stations)):
            streamlit.error("Duplicated station detected.", icon="❌")
            return False

        # Validate station format and group by station number
        pattern = r"^P(\d+)([DP])?([IO])$"
        station_groups = {}
        has_inbound = has_outbound = False

        for station in stations:
            match = re.match(pattern, str(station))
            if not match:
                streamlit.error(
                    f"Station {station} does not match required format (P + station "
                    + "number + optional D/P + ends with I/O).",
                    icon="❌",
                )
                return False

            station_num, dp_type, io_type = match.groups()
            if io_type == "I":
                has_inbound = True
            else:
                has_outbound = True

            if station_num not in station_groups:
                station_groups[station_num] = {
                    "stations": [],
                    "io_type": io_type,
                    "types": set(),
                }
            else:
                # Check IO consistency within group
                if station_groups[station_num]["io_type"] != io_type:
                    streamlit.error(
                        f"Station P{station_num} has mixed inbound/outbound ports. All ports "
                        + "must be either all inbound or all outbound.",
                        icon="❌",
                    )
                    return False

            station_groups[station_num]["stations"].append(station)
            station_groups[station_num]["types"].add(dp_type if dp_type else "mixed")

        # Validate station type combinations
        for station_num, group in station_groups.items():
            types = group["types"]
            if "mixed" in types and ("D" in types or "P" in types):
                streamlit.error(
                    "Stations that do both pick and drop cannot share station numbers with "
                    + "pick/drop station pairs.",
                    icon="❌",
                )
                return False

            # XOR check
            if bool("D" in types) != bool("P" in types):
                streamlit.error(
                    "Each pick port must have a matching drop port with the same "
                    + "station number.",
                    icon="❌",
                )
                return False

        self.stations: List[str] = stations
        self.has_inbound = has_inbound
        self.has_outbound = has_outbound
        return True

    def _display_grid(self):
        """
        Display the grid.
        """
        discrete_colourscale = [
            [0.0, "#47b39d"],
            [0.2, "#47b39d"],
            [0.2, "#ffc153"],
            [0.4, "#ffc153"],
            [0.4, "#b05f6d"],
            [0.6, "#b05f6d"],
            [0.6, "#462446"],
            [0.8, "#462446"],
            [0.8, "#2c4770"],
            [1.0, "#2c4770"],
        ]

        # Create a copy of the grid data for display
        grid_data_display = self.grid_data.copy()
        grid_data_display = pandas.DataFrame(
            numpy.where(
                grid_data_display.map(lambda x: str(x).startswith("P")),
                1,
                numpy.where(
                    grid_data_display.map(lambda x: str(x).isdigit()),
                    0,
                    numpy.where(
                        grid_data_display.map(lambda x: pandas.isna(x)),
                        4,
                        numpy.where(
                            grid_data_display.map(lambda x: str(x) == "B"), 2, 3
                        ),
                    ),
                ),
            ),
            index=grid_data_display.index,
            columns=grid_data_display.columns,
        )

        # Create a figure for the grid layout
        fig = go.Figure(
            data=go.Heatmap(
                z=grid_data_display.values,
                x=list(grid_data_display.columns),
                y=list(grid_data_display.index),
                colorscale=discrete_colourscale,
                colorbar=dict(
                    tickvals=[0, 1, 2, 3, 4],
                    ticktext=["Free", "Stations", "Buffers", "Others", "Unavailable"],
                    title="Legend",
                ),
                zmin=-0.5,
                zmax=4.5,
            )
        )

        # Add lines to indicate the grid.
        for col in range(grid_data_display.shape[1] + 1):
            fig.add_shape(
                type="line",
                x0=col + 0.5,
                x1=col + 0.5,
                y0=0.5,
                y1=grid_data_display.shape[0] + 0.5,
                line=dict(color="gray", width=1),
            )

        for row in range(grid_data_display.shape[0] + 1):
            fig.add_shape(
                type="line",
                x0=0.5,
                x1=grid_data_display.shape[1] + 0.5,
                y0=row + 0.5,
                y1=row + 0.5,
                line=dict(color="gray", width=1),
            )

        # Add arrows to indicate the desired skycar directions
        if self.desired_skycar_directions is not None:
            for _, arrow_points in self.desired_skycar_directions.groupby(
                "arrow_index"
            ):
                # Process each segment of the arrow
                for i in range(len(arrow_points) - 1):
                    from_point = arrow_points.iloc[i]
                    to_point = arrow_points.iloc[i + 1]

                    # Determine if this is the last segment (needs arrowhead)
                    is_last_segment = i == len(arrow_points) - 2

                    # Add line segment with arrowhead only for the last segment
                    fig.add_annotation(
                        x=to_point["X"],
                        y=to_point["Y"],
                        ax=from_point["X"],
                        ay=from_point["Y"],
                        xref="x",
                        yref="y",
                        axref="x",
                        ayref="y",
                        showarrow=True,
                        arrowhead=(2 if is_last_segment else 0),
                        arrowsize=1,
                        arrowwidth=1,
                        arrowcolor="black",
                        arrowside="end",
                    )

        fig.update_layout(
            title="Grid Layout",
            xaxis=dict(
                title="X",
                tickvals=list(grid_data_display.columns),
                scaleanchor="y",
                showgrid=False,
            ),
            yaxis=dict(
                title="Y",
                tickvals=list(grid_data_display.index),
                autorange="reversed",
                scaleanchor="x",
                showgrid=False,
            ),
        )
        fig.update_traces(hovertemplate="X: %{x}<br>Y: %{y}<extra></extra>")

        streamlit.plotly_chart(fig)

    def _get_desired_skycar_directions(self):
        """
        Get the desired skycar directions.
        """
        desired_skycar_directions = pandas.DataFrame(columns=["arrow_index", "X", "Y"])

        # Create a form to get the desired skycar directions to prevent constant reloading
        with streamlit.form("desired_skycar_directions"):
            streamlit.write("#### Desired skycar directions")
            streamlit.write(
                "Add desired skycar directions by adding a start point, any turning "
                + "points, and lastly an end point for each arrow individually. Leave "
                + "empty to skip."
            )
            desired_skycar_directions = streamlit.data_editor(
                desired_skycar_directions,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "arrow_index": streamlit.column_config.SelectboxColumn(
                        "Arrow index",
                        options=list(range(1, 20)),
                        width="small",
                        required=True,
                    ),
                    "X": streamlit.column_config.SelectboxColumn(
                        "X",
                        options=list(self.grid_data.columns),
                        width="small",
                        required=True,
                    ),
                    "Y": streamlit.column_config.SelectboxColumn(
                        "Y",
                        options=list(self.grid_data.index),
                        width="small",
                        required=True,
                    ),
                },
            )

            submitted_button = streamlit.form_submit_button("Add desired directions")
            if submitted_button:
                desired_skycar_directions = desired_skycar_directions.dropna(how="all")

        # Validate if the directions are horizontal or vertical only
        for arrow_index, group in desired_skycar_directions.groupby("arrow_index"):
            # Sort by index to ensure points are in order of entry
            group = group.sort_index()

            # Check if there are at least 2 points in each arrow
            if len(group) < 2:
                streamlit.error(
                    f"Arrow {arrow_index} has less than 2 points. No preferred "
                    + "direction will be added.",
                    icon="❌",
                )
                return None

            # Check each adjacent pair of points
            for i in range(len(group) - 1):
                current_point = group.iloc[i]
                next_point = group.iloc[i + 1]

                current_x, current_y = current_point["X"], current_point["Y"]
                next_x, next_y = next_point["X"], next_point["Y"]

                if (current_x != next_x and current_y != next_y) or (
                    current_x == next_x and current_y == next_y
                ):
                    streamlit.error(
                        f"Direction from ({current_x}, {current_y}) to "
                        + f"({next_x}, {next_y}) in arrow {arrow_index} is not horizontal "
                        + "or vertical. No preferred direction will be added.",
                        icon="❌",
                    )
                    return None

        self.desired_skycar_directions = desired_skycar_directions

    def _choose_linked_stations(self) -> bool:
        """
        Choose which stations are linked to each other.

        Returns
        -------
        bool
            True if the linked stations are valid, False otherwise.
        """
        streamlit.write("#### Linked stations")
        streamlit.write(
            "Link two stations so they share an inbound/outbound order. Leave empty to skip."
        )

        # Get the index of the stations from self.stations.
        station_indices = list(
            set(
                [
                    int(re.match(r"^P(\d+)([DP])?([IO])$", station).group(1))
                    for station in self.stations
                ]
            )
        )

        linked_stations_df = pandas.DataFrame(
            columns=["primary_station_index", "linked_station_index"]
        )
        linked_stations_df = streamlit.data_editor(
            linked_stations_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "primary_station_index": streamlit.column_config.SelectboxColumn(
                    "Primary station index",
                    options=station_indices,
                    width="medium",
                    required=True,
                ),
                "linked_station_index": streamlit.column_config.SelectboxColumn(
                    "Linked station index",
                    options=station_indices,
                    width="medium",
                    required=True,
                ),
            },
        )

        # Validate input
        primary_station_indices = linked_stations_df["primary_station_index"].tolist()
        linked_station_indices = linked_stations_df["linked_station_index"].tolist()

        # Check 1a and 1b: No duplicated station indices
        if len(primary_station_indices) != len(set(primary_station_indices)):
            streamlit.error("Duplicated primary station index detected.", icon="❌")
            return False
        if len(linked_station_indices) != len(set(linked_station_indices)):
            streamlit.error("Duplicated linked station index detected.", icon="❌")
            return False

        # Check 2: No primary station index found in linked station index
        for i in primary_station_indices:
            if i in linked_station_indices:
                streamlit.error(
                    "Primary station index found in linked station index.", icon="❌"
                )
                return False

        # Create a mapping of station indices to their types for faster lookup
        station_types = {}
        pattern = re.compile(r"^P(\d+)([DP])?([IO])$")

        for station in self.stations:
            match = pattern.match(station)
            station_index = int(match.group(1))
            station_type = match.group(3)
            station_types[station_index] = station_type

        # Check 3: Linked stations must have the same type
        for _, rows in linked_stations_df.iterrows():
            i = rows["primary_station_index"]
            j = rows["linked_station_index"]

            if station_types.get(i) != station_types.get(j):
                streamlit.error(
                    f"Primary station {i} and linked station {j} have different "
                    "inbound/outbound types.",
                    icon="❌",
                )
                return False

        # Get remaining station indices
        remaining_station_indices = [
            i
            for i in station_indices
            if i not in primary_station_indices and i not in linked_station_indices
        ]

        # Create station groups. Unlinked stations are grouped as a single station.
        station_code_groups = [
            [rows["primary_station_index"], rows["linked_station_index"]]
            for _, rows in linked_stations_df.iterrows()
        ] + [[i] for i in remaining_station_indices]

        self.station_code_groups = station_code_groups

        return True
