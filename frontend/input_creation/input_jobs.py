import json
from typing import List

from input_creation.input_zones import InputZonesAndStations
from core.parameters import Parameters
from ui_components.grid_designer import GridDesignerUI
from ui_components.simulation_input import SimulationInputUI



class InputJobs:
    def __init__(
        self,
        input_zones_and_stations: InputZonesAndStations,
        quantity: int,
        min_layer: int = 1,
        max_layer: int = 2,
    ):
        self.mode = "SINGLE_ROUND"
        self.allowCrossZoneGroup = False
        self.enableAutoStore = True
        self.pickFromZoneGroups = [Parameters.ZONE_NAME]
        self.minLayer = min_layer
        self.maxLayer = max_layer
        self.stations = self._get_list_of_stations(
            input_zones_and_stations=input_zones_and_stations
        )
        self.qty = quantity

    def _get_list_of_stations(
        self, input_zones_and_stations: InputZonesAndStations
    ) -> List[int]:
        return [station.code for station in input_zones_and_stations.stations]

    def to_json(
        self, save: bool = False, filename: str = "reset-job.json", type: str = "str"
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
