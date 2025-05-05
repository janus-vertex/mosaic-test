import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas
import requests
from exception import SimulationBackendException
from job_request import JobsCreationRequest
import numpy

SM_BASE_1 = "http://18.138.163.62:3020"
SM_BASE_2 = "http://18.138.163.62:3120/"


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
        self._set_server()

    def create_jobs(self):
        """
        The main method that runs the job creation in simulation.
        """
        # Create the first log entry to indicate the start of the simulation
        simulation_start_time = time.time()
        logs = pandas.DataFrame(columns=["time", "station", "bin_id", "action"])
        logs.loc[len(logs)] = {
            "time": simulation_start_time,
            "station": None,
            "bin_id": None,
            "action": "Simulation start",
        }

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
                        number_of_bins = self._get_number_of_bins(
                            station_type=station.type
                        )
                        station.bins = self._get_bins_from_order(
                            number_of_bins=number_of_bins,
                            logs=logs,
                            station_code=station.code,
                        )

                        # Call bins from matrix to the station
                        bin_ids = [bin["code"] for bin in station.bins]
                        _ = self._call_bins(station_code=station.code, bin_ids=bin_ids)
                        logs.loc[len(logs)] = {
                            "time": current_time,
                            "station": station.code,
                            "bin_id": None,
                            "action": f"{len(bin_ids)} bins called. Bin IDs: {bin_ids}",
                        }
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
                        logs.loc[len(logs)] = {
                            "time": current_time,
                            "station": station.code,
                            "bin_id": bin_id,
                            "action": "Bin stored",
                        }

                        print(f"{current_time=}, {station.code=}, {bin_id=} stored")

                        # Add delay to the next job time
                        delay = (
                            self.body.parameters.goods_in_time
                            if station.type == "I"
                            else self.body.parameters.pick_time
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
        logs.loc[len(logs)] = {
            "time": current_time,
            "station": None,
            "bin_id": None,
            "action": "Simulation end",
        }

        # Save the logs
        data_dir = Path(__file__).parents[0] / "data"
        simulation_start_datetime = time.strftime(
            "%Y-%m-%d-%H-%M-%S", time.localtime(simulation_start_time)
        )
        logs.to_csv(
            data_dir
            / "logs"
            / f"{self.body.configuration.name}_{simulation_start_datetime}.csv",
            index=False,
        )

        # Update the index file
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

        # Reset the layout to effectively stop everything after
        _ = self._reset_layout()

    def _get_number_of_bins(self, station_type: str) -> int:
        """
        Get the number of bins to call for a given station type.

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
            average_number_of_bins = self.body.parameters.goods_in_throughput
        elif station_type == "O":
            average_number_of_bins = self.body.parameters.pick_throughput
        else:
            raise SimulationBackendException(f"Invalid station type: {station_type}")

        # TODO: Use Gaussian distribution to get the number of bins, instead of dividing
        # by 2
        number_of_bins = max(int(average_number_of_bins / 2), 1)

        return number_of_bins

    def _get_bins_from_order(
        self,
        number_of_bins: int = 100,
        delay: float = 1.0,
        logs: pandas.DataFrame = None,
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
        logs : pandas.DataFrame, optional
            The logs to append the bin call to. Defaults to None.
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

        if logs is not None:
            logs.loc[len(logs)] = {
                "time": time.time(),
                "station": station_code,
                "bin_id": None,
                "action": f"No bins assigned. Number of bins per layer: {number_of_bins_per_layer}",
            }

        print(
            f"current_time={time.time()}, {station_code=}, {number_of_bins_per_layer=} assigned"
        )

        # Get bins from each layer
        bins = []
        for i, quantity in enumerate(number_of_bins_per_layer):
            if quantity > 0:
                bins.extend(
                    self._get_bins_from_layers(
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

    def _get_bins_from_layers(
        self, quantity: int, min_layer: int, max_layer: int
    ) -> List[Dict[str, Any]]:
        """
        Get bins from layers.

        Parameters
        ----------
        quantity : int
            The number of bins to get
        min_layer : int
            The minimum layer to get bins from
        max_layer : int
            The maximum layer to get bins from

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
            response = self._send_request(
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

    def _reset_layout(self) -> requests.Response:
        """
        Reset the layout of the simulation.

        Returns
        -------
        requests.Response
            The response from the server
        """
        response = self._send_request(
            url=f"{self.SM_BASE}/v3/initialize/reset",
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
        elif self.body.configuration.server_number == 2:
            self.SM_BASE = SM_BASE_2
