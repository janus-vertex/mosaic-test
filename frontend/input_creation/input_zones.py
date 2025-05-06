from __future__ import annotations

import json
from typing import List

import numpy
from core.exception import SimulationFrontendException
from core.parameters import Parameters
from ui_components.grid_designer import GridDesignerUI


class InputZonesAndStations:
    def __init__(self, grid_designer_ui: GridDesignerUI):
        self._create_zones(grid_designer_ui=grid_designer_ui)
        self._create_stations(grid_designer_ui=grid_designer_ui)

    def _create_zones(self, grid_designer_ui: GridDesignerUI):
        """
        Create zones from the grid designer UI.

        Parameters
        ----------
        grid_designer_ui : GridDesignerUI
            The grid designer UI.
        """
        # TODO: include voids for stacks less than z_size
        sm_and_tc_obstacle_voids = self._create_voids(
            grid_designer_ui=grid_designer_ui, void_type="SM and TC obstacles"
        )
        sm_obstacle_only_voids = self._create_voids(
            grid_designer_ui=grid_designer_ui, void_type="SM obstacles only"
        )
        voids = sm_and_tc_obstacle_voids + sm_obstacle_only_voids

        zone = InputZone(
            max_x=grid_designer_ui.grid_data.shape[1] - 1,
            max_y=grid_designer_ui.grid_data.shape[0] - 1,
            max_z=grid_designer_ui.z_size,
            voids=voids,
        )
        self.zones = [zone]

    def _create_voids(
        self, grid_designer_ui: GridDesignerUI, void_type: str
    ) -> List[InputVoid]:
        """
        Create voids from the grid designer UI. The voids are separated by whether they
        are exclusively SM obstacles, or SM and TC obstacles.

        Parameters
        ----------
        grid_designer_ui : GridDesignerUI
            The grid designer UI.
        void_type : str
            The type of void to create.

        Returns
        -------
        List[InputVoid]
            A list of voids.

        Raises
        ------
        NotImplementedError
            If the void type is not implemented.
        """
        if void_type == "SM and TC obstacles":
            void_mask = ~(
                grid_designer_ui.grid_data.map(lambda x: str(x).isdigit()).to_numpy()
                | grid_designer_ui.grid_data.map(
                    lambda x: str(x).startswith("P")
                ).to_numpy()
                | grid_designer_ui.grid_data.map(lambda x: str(x) == "B").to_numpy()
            )
            start_z = 0

        elif void_type == "SM obstacles only":
            void_mask = grid_designer_ui.grid_data.map(
                lambda x: str(x) == "B"
            ).to_numpy()
            start_z = 1

        else:
            raise SimulationFrontendException(f"Void type {void_type} not implemented")

        rows, cols = void_mask.shape
        voids = []

        # Use boolean array to track processed cells
        processed = numpy.zeros_like(void_mask, dtype=bool)

        # Scan unprocessed void cells
        void_positions = numpy.argwhere(numpy.logical_and(void_mask, ~processed))

        for start_y, start_x in void_positions:
            if processed[start_y, start_x]:
                continue

            # Expand right
            end_x = start_x
            while end_x + 1 < cols and void_mask[start_y, end_x + 1]:
                end_x += 1

            # Expand down
            end_y = start_y
            while end_y + 1 < rows:
                is_valid = True
                for x in range(start_x, end_x + 1):
                    if not void_mask[end_y + 1, x]:
                        is_valid = False
                        break
                if not is_valid:
                    break
                end_y += 1

            # Mark as processed
            processed[start_y : end_y + 1, start_x : end_x + 1] = True

            void = InputVoid(
                from_=Coordinates(x=int(start_x), y=int(start_y), z=start_z),
                to=Coordinates(x=int(end_x), y=int(end_y), z=grid_designer_ui.z_size),
            )
            voids.append(void)

        return voids

    def _create_stations(self, grid_designer_ui: GridDesignerUI):
        """
        Create stations from the grid designer UI.

        Parameters
        ----------
        grid_designer_ui : GridDesignerUI
            The grid designer UI.
        """
        station_height = grid_designer_ui.z_size - 2

        grid_data_array = grid_designer_ui.grid_data.to_numpy()
        grid_stations = sorted(grid_designer_ui.stations.copy())

        stations: List[InputStation] = []
        for grid_station in grid_stations:
            y, x = numpy.argwhere(grid_data_array == grid_station)[0].tolist()
            station_number = int("".join(filter(str.isdigit, grid_station)))

            if grid_station[-2] not in ["D", "P"]:
                drop = InputDropOrPick(
                    coordinates=Coordinates(x=x, y=y, z=station_height), capacity=2
                )
                pick = InputDropOrPick(
                    coordinates=Coordinates(x=x, y=y, z=station_height), capacity=1
                )
                station = InputStation(code=station_number, drop=drop, pick=pick)
                stations.append(station)
            else:
                if grid_station[-2] == "D":
                    drop = InputDropOrPick(
                        coordinates=Coordinates(x=x, y=y, z=station_height), capacity=2
                    )
                else:
                    pick = InputDropOrPick(
                        coordinates=Coordinates(x=x, y=y, z=station_height), capacity=1
                    )
                    station = InputStation(code=station_number, drop=drop, pick=pick)
                    stations.append(station)

        self.stations = stations

    def to_json(
        self, save: bool = False, filename: str = "reset-2.json", type: str = "str"
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


class InputZone:
    def __init__(
        self,
        max_x: int,
        max_y: int,
        max_z: int,
        voids: List[InputVoid],
        name: str = Parameters.ZONE_NAME,
    ):
        self.name = name
        self.fromX = 0
        self.toX = max_x
        self.fromY = 0
        self.toY = max_y
        self.fromZ = 0
        self.toZ = max_z
        self.voids = voids


class InputVoid:
    def __init__(self, from_: Coordinates, to: Coordinates):
        self.to = to

        # Since from is a reserved keyword in Python, we need to use a different way to
        # set the attribute
        setattr(self, "from", from_)


class InputStation:
    def __init__(self, code: int, drop: InputDropOrPick, pick: InputDropOrPick):
        self.code = code
        self.drop = [drop]
        self.pick = [pick]


class InputDropOrPick:
    # FIXME: What should be the value of capacity, hardware index, and zone group?
    def __init__(
        self,
        coordinates: Coordinates,
        capacity: int = 1,
        hardware_index: int = 1,
        zone_group: str = Parameters.ZONE_NAME,
    ):
        self.capacity = capacity
        self.hardwareIndex = hardware_index
        self.zoneGroup = zone_group
        self.coordinate = coordinates


class Coordinates:

    def __init__(self, x: int, y: int, z: int = 0):
        self.x = x
        self.y = y
        self.z = z
