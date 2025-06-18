import json
from core.parameters import Parameters


class InputOptimisation:
    def __init__(self):
        self.zoneGroups = [{"name": Parameters.ZONE_NAME, "isActive": True}]

    def to_json(
        self,
        save: bool = False,
        filename: str = "reset-optimisation.json",
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
