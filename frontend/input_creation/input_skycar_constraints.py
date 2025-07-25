import json
from typing import List

from ui_components.grid_designer import GridDesignerUI


class InputSkyCarConstraints:
    def __init__(self, grid_designer_ui: GridDesignerUI):
        self.constraints = self._create_constraints(grid_designer_ui=grid_designer_ui)

    def _create_constraints(self, grid_designer_ui: GridDesignerUI):

        if grid_designer_ui.desired_skycar_directions is None:
            return []

        constraints = []
        constraints_to_remove = []
        # Constraints for each arrow
        for _, arrow_points in grid_designer_ui.desired_skycar_directions.groupby(
            "arrow_index"
        ):

            arrow_points = arrow_points.drop(columns=["arrow_index"])
            current_arrow_constraints = []
            current_constraints_to_remove = []
            for i in range(len(arrow_points) - 1):
                turning_point_i = (arrow_points.iloc[i]["X"]-1, arrow_points.iloc[i]["Y"]-1)
                turning_point_j = (
                    arrow_points.iloc[i + 1]["X"]-1,
                    arrow_points.iloc[i + 1]["Y"]-1,
                )

                # Calculate the unit vector of the arrow segment
                length = max(
                    abs(turning_point_j[0] - turning_point_i[0]),
                    abs(turning_point_j[1] - turning_point_i[1]),
                )
                unit_vector = (
                    int((turning_point_j[0] - turning_point_i[0]) / length),
                    int((turning_point_j[1] - turning_point_i[1]) / length),
                )

                for step in range(1, length + 1):
                    # Skip for the last turning point (end) of the arrow
                    if i == len(arrow_points) - 2 and step == length:
                        # Remove the constraint of the same direction for the end of the arrow
                        constraint_to_remove = turning_point_j + (
                            turning_point_j[0] - unit_vector[0],
                            turning_point_j[1] - unit_vector[1],
                        )
                        current_constraints_to_remove.append(constraint_to_remove)
                        break

                    point = (
                        turning_point_i[0] + step * unit_vector[0],
                        turning_point_i[1] + step * unit_vector[1],
                    )
                    constraints_from_point = [
                        (point[0] + 1, point[1]) + point,
                        (point[0] - 1, point[1]) + point,
                        (point[0], point[1] + 1) + point,
                        (point[0], point[1] - 1) + point,
                        point + (point[0] + 1, point[1]),
                        point + (point[0] - 1, point[1]),
                        point + (point[0], point[1] + 1),
                        point + (point[0], point[1] - 1),
                    ]

                    # Remove the constrant that is the same direction as the arrow
                    # segment
                    constraint_to_remove = point + (
                        point[0] - unit_vector[0],
                        point[1] - unit_vector[1],
                    )
                    current_constraints_to_remove.append(constraint_to_remove)

                    current_arrow_constraints.extend(constraints_from_point)

            constraints.extend(current_arrow_constraints)
            constraints_to_remove.extend(current_constraints_to_remove)

        # Make sure no repeats in constraints and constraints_to_remove lists
        constraints_set = set(constraints)
        constraints_to_remove_set = set(constraints_to_remove)
        constraints = list(constraints_set - constraints_to_remove_set)

        # Convert contraints from tuple to list
        constraints = sorted([list(constraint) for constraint in constraints])

        return constraints

    def to_json(
        self,
        save: bool = False,
        filename: str = "reset-constraints.json",
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
