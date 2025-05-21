import time
from typing import Any, Dict, List, Optional

import numpy
import requests
from exception import SimulationBackendException
from job_request import JobsCreationRequest
from simulation_database import SimulationDatabase

SM_BASE_1 = "http://18.138.163.62:3020"
TC_BASE_1 = "http://13.228.83.247:3030"

SM_BASE_2 = "http://18.138.163.62:3120/"
TC_BASE_2 = "http://13.228.83.247:3033/"


class Station:
    """
    Station class.

    Attributes
    ----------
    code : int
        The code of the station
    type : str
        The type of the station, either "I" (inbound) or "O" (outbound)
    bins : List[Dict[str, Any]]
        The list of bins assigned to the station
    next_job_time : float
        The time of the next job for the station
    """

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
    """
    JobService class.

    Attributes
    ----------
    body : JobsCreationRequest
        The request body
    status : Dict[str, Any]
        The status of the job creation
    SM_BASE : str
        The base URL of the simulation server
    """

    def __init__(
        self,
        jobs_creation_request: JobsCreationRequest,
        job_creation_status: Dict[str, Any],
    ):
        self.body = jobs_creation_request
        self.status = job_creation_status
        self.simulation_run_id = None
        self.simulation_database = None
        self._set_server()

    def create_jobs(self):
        """
        The main method that runs the job creation in simulation.
        """
        self.simulation_database = SimulationDatabase()
        self.simulation_run_id = self.body.configuration.id

        simulation_start_time = time.time()
        self.simulation_database.update_simulation_run_timestamp(
            simulation_run_id=self.simulation_run_id,
            start_timestamp=simulation_start_time,
        )

        # Create the first log entry to indicate the start of the simulation
        self.simulation_database.log_action(
            timestamp=simulation_start_time,
            simulation_run_id=self.simulation_run_id,
            action="Simulation start",
        )

        # Create a list of station instances from stations in the request
        station_list = [
            Station(code=station.code, type=station.type)
            for station in self.body.stations
        ]

        # Initialize current time and check time interval
        current_time = time.time()
        next_check_time = current_time
        check_time_interval = 1.0

        # Main loop that runs until the stop request is made or the simulation duration
        # is reached
        while (
            not self.status["stop_requested"]
            and current_time
            <= simulation_start_time + self.body.configuration.duration_in_seconds
        ):
            current_time = time.time()

            if current_time >= next_check_time:
                for station in station_list:
                    # If there are no more bins for the station, find new bins and call
                    # them from the matrix
                    if len(station.bins) == 0:
                        number_of_bins = self._get_number_of_bins_per_order(
                            station_type=station.type
                        )
                        station.bins = self._get_bins_from_order(
                            number_of_bins=number_of_bins, station_code=station.code
                        )

                        # Call bins from matrix to the station
                        bin_ids = [bin["code"] for bin in station.bins]
                        _ = self._call_bins(station_code=station.code, bin_ids=bin_ids)

                        self.simulation_database.log_action(
                            timestamp=time.time(),
                            simulation_run_id=self.simulation_run_id,
                            station_code=station.code,
                            action=f"{len(bin_ids)} bins called. Bin IDs: {bin_ids}",
                        )

                        print(f"{current_time=}, {station.code=}, {bin_ids=} called")

                    # Check station status at intervals to see if a bin is at station
                    station_status = self._check_station_status(station.code)
                    status_with_bin_at_station = next(
                        (
                            data_item
                            for data_item in station_status
                            if data_item["lastMovement"] == "AT_STATION_WORK"
                        ),
                        None,
                    )

                    # If a bin is at station and the time to store the bin has come
                    if (
                        status_with_bin_at_station is not None
                        and current_time >= station.next_job_time
                    ):
                        # Store the bin at station back to matrix
                        bin_id = status_with_bin_at_station["code"]
                        _ = self._store_bin(station_code=station.code, bin_id=bin_id)

                        self.simulation_database.log_action(
                            timestamp=time.time(),
                            simulation_run_id=self.simulation_run_id,
                            station_code=station.code,
                            bin_code=bin_id,
                            action="Bin stored",
                        )
                        print(f"{current_time=}, {station.code=}, {bin_id=} stored")

                        # Add delay to the next job time
                        delay = (
                            self.body.parameters.inbound_time
                            if station.type == "I"
                            else self.body.parameters.outbound_time
                        )
                        station.next_job_time = current_time + delay

                        # Remove the stored bin from the list of bins assigned to the
                        # station
                        bin_to_remove = next(
                            (bin for bin in station.bins if bin["code"] == bin_id), None
                        )

                        # Sanity check: this should never happen
                        if bin_to_remove is None:
                            raise SimulationBackendException(
                                f"Bin {bin_id} not found at station {station.code}"
                            )

                        station.bins.remove(bin_to_remove)

                next_check_time = current_time + check_time_interval

            # Sleep for 0.5 seconds to avoid busy-waiting
            time.sleep(0.5)

        # Create the last log entry to indicate the end of the simulation
        self.status["stop_time"] = current_time
        self.simulation_database.log_action(
            timestamp=current_time,
            simulation_run_id=self.simulation_run_id,
            action="Simulation end",
        )

        # Update the simulation run end timestamp
        self.simulation_database.update_simulation_run_timestamp(
            simulation_run_id=self.simulation_run_id,
            end_timestamp=current_time,
        )

        # Close the simulation database connection
        self.simulation_database.close_connection()

        # Stop TC to effectively stop everything
        _ = self._tc_stop()

    def _get_number_of_bins_per_order(self, station_type: str) -> int:
        """
        Get the number of bins per order to call for a given station type. We assume
        this number given is the peak number of bins per order, so the simulation is
        always simulating the busiest scenario.

        Parameters
        ----------
        station_type : str
            The type of the station, either "I" (inbound) or "O" (outbound)

        Raises
        ------
        SimulationBackendException
            If the station type is invalid

        Returns
        -------
        int
            The number of bins to call for the given station type
        """
        if station_type == "I":
            number_of_bins_per_order = self.body.parameters.inbound_bins_per_order
        elif station_type == "O":
            number_of_bins_per_order = self.body.parameters.outbound_bins_per_order
        else:
            raise SimulationBackendException(f"Invalid station type: {station_type}")

        return number_of_bins_per_order

    def _get_bins_from_order(
        self,
        number_of_bins: int = 100,
        delay: float = 1.0,
        station_code: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Get bins from the order.

        Parameters
        ----------
        number_of_bins : int, optional
            The number of bins to get. Defaults to 100.
        delay : float, optional
            The delay between each bin call to avoid busy-waiting. Defaults to 1.0
            second.
        station_code : int, optional
            The code of the station to append the bin call to. Defaults to None.

        Returns
        -------
        List[Dict[str, Any]]
            The list of bins

        Raises
        ------
        SimulationBackendException
            - If the number of bins is less than 1
            - If there is no bin after querying the layers
        """
        if number_of_bins < 1:
            raise SimulationBackendException(f"{number_of_bins=}; must be at least 1")

        # Use pareto probabilities as weights to randomly sample layer indices
        weights = numpy.array(self.body.parameters.pareto_probabilities)
        weights = weights / weights.sum()
        layer_indices = numpy.random.choice(
            len(weights), size=number_of_bins, p=weights
        )

        # Count occurrences of each layer index
        number_of_bins_per_layer = [
            int(numpy.sum(layer_indices == i)) for i in range(len(weights))
        ]

        self.simulation_database.log_action(
            timestamp=time.time(),
            simulation_run_id=self.simulation_run_id,
            station_code=station_code,
            action=f"No bins assigned. Number of bins per layer: {number_of_bins_per_layer}",
        )

        print(
            f"current_time={time.time()}, {station_code=}, {number_of_bins_per_layer=} assigned"
        )

        # Get bins from each layer
        bins = []
        for i, quantity in enumerate(number_of_bins_per_layer):
            if quantity > 0:
                bins_in_this_layer = self._get_bins_from_layers(
                    min_layer=i + 1,
                    max_layer=i + 1,
                )
                quantity_to_sample = min(quantity, len(bins_in_this_layer))
                # Randomly sample bins from this layer
                if quantity_to_sample > 0:
                    sampled_indices = numpy.random.choice(
                        len(bins_in_this_layer), size=quantity_to_sample, replace=False
                    )
                    sampled_bins = [bins_in_this_layer[i] for i in sampled_indices]
                    bins.extend(sampled_bins)

                time.sleep(delay)

        if len(bins) == 0:
            raise SimulationBackendException(
                "No bins are available. Either they are physically unavailble, or API "
                + "is down."
            )

        # Make sure the bin codes are unique. Only keep the first occurrence of each bin.
        unique_bins = []
        unique_bin_codes = set()
        for bin in bins:
            if bin["code"] not in unique_bin_codes:
                unique_bins.append(bin)
                unique_bin_codes.add(bin["code"])

        return unique_bins

    def _get_bins_from_layers(
        self, min_layer: int, max_layer: int, quantity: int | None = None
    ) -> List[Dict[str, Any]]:
        """
        Get bins from layers.

        Parameters
        ----------
        min_layer : int
            The minimum layer to get bins from
        max_layer : int
            The maximum layer to get bins from
        quantity : int, optional
            The number of bins to get. Defaults to None, which means all bins in the
            layers are returned.

        Returns
        -------
        List[Dict[str, Any]]
            The list of bins.

            If the request fails, either due to number of bins available in the
            layer(s) are lower than the queried quantity, or bins do not exist in
            the specified layer(s), or other unintended network reasons, then an
            empty list is returned.
        """
        try:
            data = {
                "minLayer": min_layer,
                "maxLayer": max_layer,
            }
            if quantity is not None:
                data["qty"] = quantity
            response = self._send_request(
                url=f"{self.SM_BASE}/v3/storages/layer",
                method="GET",
                data=data,
            )
            return response.json()["data"]

        except requests.exceptions.RequestException as e:
            return []

    def _check_station_status(self, station_code: int) -> List[Dict[str, Any]]:
        """
        Check the status of the station.

        Parameters
        ----------
        station_code : int
            The code of the station

        Returns
        -------
        List[Dict[str, Any]]
            The status of the station. A successful request returns a list of at
            most two dictionaries, one indicates the bin at station and the other
            indicates the bin at gateway. If no bin is at station, the list is empty.
        """
        response = self._send_request(
            url=f"{self.SM_BASE}/v3/storages?stations={station_code}",
            method="GET",
        )
        return response.json()["data"]

    def _call_bins(self, station_code: int, bin_ids: List[int]) -> Dict[str, Any]:
        """
        Call bins from matrix to the station.

        Parameters
        ----------
        station_code : int
            The code of the station
        bin_ids : List[int]
            The list of bin IDs to call

        Returns
        -------
        Dict[str, Any]
            The response from the server
        """
        response = self._send_request(
            url=f"{self.SM_BASE}/v3/operations/call",
            method="POST",
            data={"station": station_code, "storages": bin_ids},
        )
        return response.json()

    def _store_bin(self, station_code: int, bin_id: int) -> Dict[str, Any]:
        """
        Store a bin at the station back to matrix.

        Parameters
        ----------
        station_code : int
            The code of the station
        bin_id : int
            The ID of the bin to store

        Returns
        -------
        Dict[str, Any]
            The response from the server
        """
        response = self._send_request(
            url=f"{self.SM_BASE}/v3/operations/store",
            method="POST",
            data={
                "station": station_code,
                "storage": bin_id,
            },
        )
        return response.json()

    def _tc_stop(self) -> requests.Response | None:
        response = self._send_request(
            url=f"{self.TC_BASE}/operation/cyclestop",
            data={
                "status": "Enabled",
                "reason": "Matrix simulation has stopped the simulation.",
            },
        )
        return response

    @staticmethod
    def _send_request(
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
        """
        Set the base URL of the simulation server.
        """
        if self.body.configuration.server_number == 1:
            self.SM_BASE = SM_BASE_1
            self.TC_BASE = TC_BASE_1
        elif self.body.configuration.server_number == 2:
            self.SM_BASE = SM_BASE_2
            self.TC_BASE = TC_BASE_2
