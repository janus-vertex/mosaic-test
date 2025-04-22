import time
from typing import Any, Dict, List, Optional

import numpy
import requests
from exception import SimulationBackendException
from job_request import JobsCreationRequest

SM_BASE_1 = "http://18.138.163.62:3020"
SM_BASE_2 = "http://54.251.49.145:3020"


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
        bin_ids = self.get_all_bin_ids(order_line_quantity=order_line_quantity)

        station_bin_allocation = self.allocate_bins_to_stations(bin_ids=bin_ids)

        next_check_time = time.time() + 1.0
        print(next_check_time)

        while not self.status["stop_requested"]:
            current_time = time.time()
            print(f"Current time: {current_time}, Number of bin IDs: {len(bin_ids)}")

            if current_time >= next_check_time:

                # TODO: Logic sets here
                if not bin_ids:
                    bin_ids = self.get_all_bin_ids(
                        order_line_quantity=order_line_quantity
                    )

                bin_ids = bin_ids[:-1]

                next_check_time = current_time + 1.0
                print(next_check_time)

            time.sleep(0.5)

    def allocate_bins_to_stations(
        self,
        bin_ids: List[Dict[str, Any]],
    ) -> Dict[int, List[Dict[str, Any]]]:

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
        inbound_size = int(inbound_ratio * len(bin_ids))

        # Use array indexing for more efficient splitting
        indices = numpy.arange(len(bin_ids))
        numpy.random.shuffle(indices)

        bins_for_inbound = numpy.array(bin_ids)[indices[:inbound_size]]
        bins_for_outbound = numpy.array(bin_ids)[indices[inbound_size:]]

        # Allocate bins evenly among inbound stations
        bins_per_inbound_station = len(bins_for_inbound) // len(inbound_stations)
        remainder_inbound = len(bins_for_inbound) % len(inbound_stations)

        inbound_allocation = {}
        start_idx = 0
        for i, station in enumerate(inbound_stations):
            # Add one extra bin for stations until remainder is used up
            extra = 1 if i < remainder_inbound else 0
            end_idx = start_idx + bins_per_inbound_station + extra
            inbound_allocation[station.code] = bins_for_inbound[start_idx:end_idx]
            start_idx = end_idx

        # Allocate bins evenly among outbound stations
        bins_per_outbound_station = len(bins_for_outbound) // len(outbound_stations)
        remainder_outbound = len(bins_for_outbound) % len(outbound_stations)

        outbound_allocation = {}
        start_idx = 0
        for i, station in enumerate(outbound_stations):
            # Add one extra bin for stations until remainder is used up
            extra = 1 if i < remainder_outbound else 0
            end_idx = start_idx + bins_per_outbound_station + extra
            outbound_allocation[station.code] = bins_for_outbound[start_idx:end_idx]
            start_idx = end_idx

        # Combine inbound and outbound allocations into a single dictionary
        station_bin_allocation = {**inbound_allocation, **outbound_allocation}

        return station_bin_allocation

    def get_bin_ids_from_layers(
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

    def get_all_bin_ids(
        self, order_line_quantity: int = 100, delay: float = 1.0
    ) -> List[Dict[str, Any]]:
        order_line_per_layer = [
            int(max(percentage / 100 * order_line_quantity, 1))
            for percentage in self.body.parameters.pareto_percentages
        ]
        print(order_line_per_layer)

        bin_ids = []
        for i, quantity in enumerate(order_line_per_layer):
            bin_ids.extend(
                self.get_bin_ids_from_layers(
                    quantity=quantity,
                    min_layer=i + 1,
                    max_layer=i + 1,
                )
            )
            time.sleep(delay)

        if len(bin_ids) == 0:
            raise SimulationBackendException(
                "No bins are available. Either they are physically unavailble, or API "
                + "is down."
            )

        return bin_ids

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
