import json

from ui_components.simulation_input import SimulationInputUI
from ui_components.grid_designer import GridDesignerUI
from input_creation.input_zones import InputZonesAndStations
from input_creation.input_simulation import InputSimulation


class InputDatabase:
    def __init__(
        self,
        simulation_input_ui: SimulationInputUI,
        grid_designer_ui: GridDesignerUI,
        input_zones_and_stations: InputZonesAndStations,
        input_simulation: InputSimulation,
    ):

        self.simulation_name = simulation_input_ui.simulation_name
        self.inbound_bins_per_order = simulation_input_ui.inbound_bins_per_order
        self.outbound_bins_per_order = simulation_input_ui.outbound_bins_per_order
        self.inbound_orders_per_hour = simulation_input_ui.inbound_orders_per_hour
        self.outbound_orders_per_hour = simulation_input_ui.outbound_orders_per_hour
        self.number_of_skycars = simulation_input_ui.number_of_skycars
        self.inbound_handling_time = simulation_input_ui.inbound_time
        self.outbound_handling_time = simulation_input_ui.outbound_time
        self.pareto_p = simulation_input_ui.pareto_p
        self.pareto_q = simulation_input_ui.pareto_q
        self.number_of_bins = grid_designer_ui.number_of_bins
        self.stations_string = self._encode_stations(
            input_zones_and_stations=input_zones_and_stations,
            input_simulation=input_simulation,
        )
        self.duration_string = simulation_input_ui.duration_string
        self.station_groups_string = self._encode_station_groups(
            input_simulation=input_simulation
        )
        self.desired_skycar_directions_string = self._encode_desired_skycar_directions(
            grid_designer_ui=grid_designer_ui
        )

    def _encode_desired_skycar_directions(self, grid_designer_ui: GridDesignerUI) -> str:
        return_str = ""
        for _, row in grid_designer_ui.desired_skycar_directions.iterrows():
            return_str += f"{row['arrow_index']}:{row['X']},{row['Y']};"
        return return_str[:-1]

    def _encode_station_groups(self, input_simulation: InputSimulation) -> str:
        return_str = ""
        for group in input_simulation.station_groups:
            return_str += (
                f"{group.group}:"
                + ",".join(str(code) for code in group.station_codes)
                + ";"
            )
        return return_str[:-1]

    def _encode_stations(
        self,
        input_zones_and_stations: InputZonesAndStations,
        input_simulation: InputSimulation,
    ) -> str:
        # Get stations from both inputs
        stations_from_input_zones_and_stations = input_zones_and_stations.stations
        stations_from_input_simulation = input_simulation.stations

        # Build station strings
        station_segments = []
        for station_item in stations_from_input_zones_and_stations:
            code = station_item.code
            station_type = next(
                (x.type for x in stations_from_input_simulation if x.code == code),
                None,
            )

            if station_type is None:
                raise ValueError(f"Station type not found for code: {code}")

            # Get coordinates
            drop_coords = (
                station_item.drop[0].coordinate.x,
                station_item.drop[0].coordinate.y,
            )
            pick_coords = (
                station_item.pick[0].coordinate.x,
                station_item.pick[0].coordinate.y,
            )

            # Format the station string
            station_str = (
                f"{code}{station_type}:"
                f"D(x{drop_coords[0]}y{drop_coords[1]})"
                f"P(x{pick_coords[0]}y{pick_coords[1]})"
            )
            station_segments.append(station_str)

        # Join all station segments with semicolons
        return ";".join(station_segments)

    def to_json(
        self,
        save: bool = False,
        filename: str = "reset-database.json",
        type: str = "str",
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
