import json


class InputSkyCarSetup:
    def __init__(self, number_of_skycars: int, model: str):
        self.num_skycars = number_of_skycars
        self.model = model

    def to_json(
        self, save: bool = False, filename: str = "reset-5.json", type: str = "str"
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


if __name__ == "__main__":
    a = InputSkyCarSetup()
    print(a.to_json(save=True))
