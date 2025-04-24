import time
from typing import Any, Dict, List, Optional

import numpy
import requests
from exception import SimulationBackendException
from job_request import JobsCreationRequest

SM_BASE_1 = "http://18.138.163.62:3020"
SM_BASE_2 = "http://18.138.163.62:3120/"


class Station:
    def __init__(
        self, code: int, type: str, bins: List[Dict[str, Any]], next_job_time: float = 0
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

    def create_jobs(self, order_line_quantity: int = 20):
        # Initial setup
        bins = self.get_bins_from_order(
            order_line_quantity=order_line_quantity, delay=0.1
        )
        allocation = self.allocate_bins_to_stations(bins=bins)

        next_check_time = time.time() + 1.0
        print(f"Next check time: {next_check_time}")

        while not self.status["stop_requested"]:
            current_time = time.time()
            print(f"Current time: {current_time}")

            for station in allocation:
                print(f"Station {station.code} ({station.type}): {len(station.bins)}")


            # Initiate call bins first 
            for station in allocation:
                if station.type == "O":
                    bin_ids = [bin["code"] for bin in station.bins]
                    _ = self.call_bins(station_code=station.code, bin_ids=bin_ids)


            if current_time >= next_check_time:
                for station in allocation:
                    station_status = self.check_station_status(station.code)

                    if (
                        len(station_status) == 0
                        and station.type == "I"
                        and current_time >= station.next_job_time
                        and len(station.bins) > 0
                    ):
                        bin_id = station.bins[0]["code"]
                        _ = self.store_bin(
                            station_code=station.code,
                            bin_id=bin_id,
                        )
                        station.next_job_time = (
                            current_time + self.body.parameters.goods_in_time
                        )

                        station.bins = station.bins[1:]

                    if (
                        len(station_status) == 0
                        and station.type == "O"
                        and current_time >= station.next_job_time
                    ):
                        station.next_job_time = (
                            current_time + self.body.parameters.pick_time
                        )

                next_check_time = current_time + 1.0
                print(f"Next check time: {next_check_time}")

            time.sleep(0.5)

    def allocate_bins_to_stations(
        self,
        bins: List[Dict[str, Any]],
    ) -> List[Station]:

        inbound_stations = [
            station for station in self.body.stations if station.type == "I"
        ]
        outbound_stations = [
            station for station in self.body.stations if station.type == "O"
        ]
        number_of_inbound_stations = len(inbound_stations)
        number_of_outbound_stations = len(outbound_stations)

        # Allocate bins to respective stations according to inbound and outbound ratios
        inbound_ratio = (
            number_of_inbound_stations
            * self.body.parameters.goods_in_throughput
            / (
                number_of_inbound_stations * self.body.parameters.goods_in_throughput
                + number_of_outbound_stations * self.body.parameters.pick_throughput
            )
        )

        # Calculate size for inbound bins
        inbound_size = int(inbound_ratio * len(bins))

        # Use array indexing for more efficient splitting
        indices = numpy.arange(len(bins))
        numpy.random.shuffle(indices)

        bins_for_inbound = numpy.array(bins)[indices[:inbound_size]]
        bins_for_outbound = numpy.array(bins)[indices[inbound_size:]]

        allocation = []

        # Allocate bins evenly among inbound stations
        bins_per_inbound_station = len(bins_for_inbound) // len(inbound_stations)
        remainder_inbound = len(bins_for_inbound) % len(inbound_stations)

        start_idx = 0
        for i, station in enumerate(inbound_stations):
            # Add one extra bin for stations until remainder is used up
            extra = 1 if i < remainder_inbound else 0
            end_idx = start_idx + bins_per_inbound_station + extra
            allocation.append(
                Station(
                    code=station.code,
                    type=station.type,
                    bins=bins_for_inbound[start_idx:end_idx],
                )
            )
            start_idx = end_idx

        # Allocate bins evenly among outbound stations
        bins_per_outbound_station = len(bins_for_outbound) // len(outbound_stations)
        remainder_outbound = len(bins_for_outbound) % len(outbound_stations)

        start_idx = 0
        for i, station in enumerate(outbound_stations):
            # Add one extra bin for stations until remainder is used up
            extra = 1 if i < remainder_outbound else 0
            end_idx = start_idx + bins_per_outbound_station + extra
            allocation.append(
                Station(
                    code=station.code,
                    type=station.type,
                    bins=bins_for_outbound[start_idx:end_idx],
                )
            )
            start_idx = end_idx

        return sorted(allocation, key=lambda station: station.code)

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
        print(order_line_per_layer)

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
