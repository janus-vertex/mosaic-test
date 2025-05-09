import json
from typing import List
from ui_components.simulation_input import SimulationInputUI
from input_creation.input_zones import InputZonesAndStations


class InputDelay:
    def __init__(
        self,
        simulation_input_ui: SimulationInputUI,
        input_zones_and_stations: InputZonesAndStations,
    ):
        self.action = "DISABLE"
        self.stations = self._get_list_of_stations(
            input_zones_and_stations=input_zones_and_stations
        )

    def _get_list_of_stations(
        self, input_zones_and_stations: InputZonesAndStations
    ) -> List[int]:
        return [station.code for station in input_zones_and_stations.stations]

    def to_json(
        self, save: bool = False, filename: str = "reset-delay.json", type: str = "str"
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
