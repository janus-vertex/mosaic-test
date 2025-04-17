import json

import numpy
import pandas

from core.parameters import Parameters
from ui_components.grid_designer import GridDesignerUI


class InputSMObstacles:
    def __init__(self, grid_designer_ui: GridDesignerUI):
        self._create_stacks(grid_designer_ui=grid_designer_ui)
        self.zoneGroup = Parameters.ZONE_NAME
        self.isSkycarAccessible = False

    def _create_stacks(self, grid_designer_ui: GridDesignerUI):
        void_mask = ~(
            grid_designer_ui.grid_data.map(lambda x: str(x).isdigit()).to_numpy()
            | grid_designer_ui.grid_data.map(
                lambda x: str(x).startswith("P")
            ).to_numpy()
            # | grid_designer_ui.grid_data.map(lambda x: str(x) == "B").to_numpy()
        )
        # Get coordinates where void_mask is True
        coordinates = numpy.argwhere(void_mask)
        
        # Create InputStack objects for each coordinate
        self.stacks = [
            InputStack(x=int(col), y=int(row)) 
            for row, col in coordinates
        ]

    def to_json(
        self, save: bool = False, filename: str = "reset-3.json", type: str = "str"
    ) -> str:
        json_str = json.dumps(
            self, default=lambda o: o.__dict__, sort_keys=True, indent=4
        )

        if save:
            with open(filename, "w") as file:
                file.write(json_str)

        if type == "str":
            return json_str
        elif type == "dict":
            return json.loads(json_str)


class InputStack:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
