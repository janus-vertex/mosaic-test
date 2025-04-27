import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas
import requests
from exception import SimulationBackendException
from job_request import JobsCreationRequest

SM_BASE_1 = "http://18.138.163.62:3020"
SM_BASE_2 = "http://18.138.163.62:3120/"


class Station:
    def __init__(
        self,
        code: int,
        type: str,
        bins: List[Dict[str, Any]] = [],
        next_job_time: float = 0,
    ):
        self.code = code
        self.type = type
        self.bins = bins
        self.next_job_time = next_job_time


class JobService:
    def __init__(
        self,
        jobs_creation_request: JobsCreationRequest,
        job_creation_status: Dict[str, Any],
    ):
        self.body = jobs_creation_request
        self.status = job_creation_status
        self._set_server()

    def create_jobs(self):

        station_list = [
            Station(code=station.code, type=station.type)
            for station in self.body.stations
        ]

        simulation_start_time = time.time()

        # Convert simulation start time from Unix timestamp to datetime format
        simulation_start_datetime = time.strftime(
            "%Y-%m-%d-%H-%M-%S", time.localtime(simulation_start_time)
        )
        logs = pandas.DataFrame(columns=["time", "station", "bin_id", "action"])

        logs.loc[len(logs)] = {
            "time": simulation_start_time,
            "station": None,
            "bin_id": None,
            "action": "Simulation start",
        }

        current_time = time.time()
        next_check_time = current_time + 1.0
        while (
            not self.status["stop_requested"]
            and current_time
            <= simulation_start_time + self.body.configuration.duration_in_seconds
        ):
            current_time = time.time()

            # print(f"{current_time=}")

            if current_time >= next_check_time:
                for station in station_list:

                    # If there are no more bins for the station, find new bins and call
                    # them from the matrix
                    if len(station.bins) == 0:
                        print(f"No bins for station {station.code}")

                        average_number_of_bins = max(
                            int(
                                (
                                    self.body.parameters.goods_in_throughput
                                    if station.type == "I"
                                    else (
                                        self.body.parameters.pick_throughput
                                        if station.type == "O"
                                        else None
                                    )
                                )
                            ),
                            1,
                        )

                        if average_number_of_bins is None:
                            raise SimulationBackendException(
                                f"Average number of bins is None for station {station.code}"
                            )

                        station.bins = self.get_bins_from_order(
                            order_line_quantity=average_number_of_bins
                        )

                        # Call bins for station
                        bin_ids = [bin["code"] for bin in station.bins]
                        print(f"{bin_ids=}")

                        _ = self.call_bins(station_code=station.code, bin_ids=bin_ids)
                        logs.loc[len(logs)] = {
                            "time": current_time,
                            "station": station.code,
                            "bin_id": None,
                            "action": f"{len(bin_ids)} bins called",
                        }

                    station_status = self.check_station_status(station.code)
                    status_with_bin_at_station = next(
                        (
                            data_item
                            for data_item in station_status
                            if data_item["lastMovement"] == "AT_STATION_WORK"
                        ),
                        None,
                    )
                    if (
                        status_with_bin_at_station is not None
                        and current_time >= station.next_job_time
                    ):
                        bin_id = status_with_bin_at_station["code"]
                        print(f"{bin_id=} {station.code=} to be stored")
                        _ = self.store_bin(station_code=station.code, bin_id=bin_id)

                        logs.loc[len(logs)] = {
                            "time": current_time,
                            "station": station.code,
                            "bin_id": bin_id,
                            "action": "Bin stored",
                        }

                        delay = (
                            self.body.parameters.goods_in_time
                            if station.type == "I"
                            else self.body.parameters.pick_time
                        )
                        station.next_job_time = current_time + delay

                        bin_to_remove = next(
                            (bin for bin in station.bins if bin["code"] == bin_id), None
                        )

                        if bin_to_remove is None:
                            raise SimulationBackendException(
                                f"Bin {bin_id} not found at station {station.code}"
                            )

                        station.bins.remove(bin_to_remove)
                        print(
                            f"Bins on station {station.code}: {[bin['code'] for bin in station.bins]}"
                        )

                next_check_time = current_time + 1.0

                # print(f"{next_check_time=}")

            time.sleep(0.5)

        self.status["stop_time"] = current_time

        logs.loc[len(logs)] = {
            "time": current_time,
            "station": None,
            "bin_id": None,
            "action": "Simulation end",
        }

        data_dir = Path(__file__).parents[0] / "data"
        logs.to_csv(
            data_dir
            / "logs"
            / f"{self.body.configuration.name}_{simulation_start_datetime}.csv",
            index=False,
        )

        index_df = pandas.read_csv(data_dir / "index.csv")
        index_df.loc[len(index_df)] = {
            "name": self.body.configuration.name,
            "start_time": simulation_start_datetime,
            "end_time": time.strftime(
                "%Y-%m-%d-%H-%M-%S", time.localtime(current_time)
            ),
            "server": self.body.configuration.server_number,
        }
        index_df.to_csv(data_dir / "index.csv", index=False)

    def get_bins_from_layers(
        self, quantity: int, min_layer: int, max_layer: int
    ) -> List[Dict[str, Any]]:
        try:
            response = self.send_request(
                url=f"{self.SM_BASE}/v3/storages/layer",
                method="GET",
                data={
                    "qty": quantity,
                    "minLayer": min_layer,
                    "maxLayer": max_layer,
                },
            )
            return response.json()["data"]

        except requests.exceptions.RequestException as e:
            return []

    def get_bins_from_order(
        self, order_line_quantity: int = 100, delay: float = 1.0
    ) -> List[Dict[str, Any]]:
        order_line_per_layer = [
            int(max(percentage / 100 * order_line_quantity, 1))
            for percentage in self.body.parameters.pareto_percentages
        ]
        # print(order_line_per_layer)

        bins = []
        for i, quantity in enumerate(order_line_per_layer):
            bins.extend(
                self.get_bins_from_layers(
                    quantity=quantity,
                    min_layer=i + 1,
                    max_layer=i + 1,
                )
            )
            time.sleep(delay)

        if len(bins) == 0:
            raise SimulationBackendException(
                "No bins are available. Either they are physically unavailble, or API "
                + "is down."
            )

        return bins

    def store_bin(self, station_code: int, bin_id: int):
        response = self.send_request(
            url=f"{self.SM_BASE}/v3/operations/store",
            method="POST",
            data={
                "station": station_code,
                "storage": bin_id,
            },
        )
        return response.json()

    def check_station_status(self, station_code: int):
        response = self.send_request(
            url=f"{self.SM_BASE}/v3/storages?stations={station_code}",
            method="GET",
        )
        return response.json()["data"]

    def call_bins(self, station_code: int, bin_ids: List[int]):
        response = self.send_request(
            url=f"{self.SM_BASE}/v3/operations/call",
            method="POST",
            data={"station": station_code, "storages": bin_ids},
        )
        return response.json()

    @staticmethod
    def send_request(
        url: str,
        method: str = "POST",
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        timeout: int | None = None,
    ) -> requests.Response:
        """
        Send an HTTP request to the specified endpoint.

        Parameters
        ----------
        endpoint : str
            The API endpoint to send the request to
        method : str, optional
            The HTTP method to use (GET, POST, PUT, DELETE, etc.)
        data : Dict[str, Any], optional
            The data to send in the request body
        params : Dict[str, Any], optional
            The URL parameters to include
        headers : Dict[str, Any], optional
            The headers to include in the request
        timeout : int, optional
            The timeout for the request

        Returns
        -------
        requests.Response
            The response from the server

        Raises
        ------
        requests.exceptions.RequestException
            If the request fails
        """

        if headers is None:
            headers = {"Content-Type": "application/json"}

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                json=data,
                params=params,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            print(f"Request failed: {str(e)}")
            raise

    def _set_server(self):
        if self.body.configuration.server_number == 1:
            self.SM_BASE = SM_BASE_1
        elif self.body.configuration.server_number == 2:
            self.SM_BASE = SM_BASE_2
