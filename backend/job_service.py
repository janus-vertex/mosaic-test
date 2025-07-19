import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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
        advance_order_name: str = None,
    ):
        self.code = code
        self.type = type
        self.bins = bins
        self.next_job_time = next_job_time
        self.advance_order_name = advance_order_name


class StationGroup:
    def __init__(self, group: int, stations: List[Station]):
        self.group = group
        self.stations = stations
        self.type = stations[0].type


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
        self.simulation_start_time = simulation_start_time

        # Create the first log entry to indicate the start of the simulation
        self._log("Simulation starts", timestamp=simulation_start_time)

        # Create a list of station instances from stations in the request
        station_list = [
            Station(code=station.code, type=station.type)
            for station in self.body.stations
        ]

        # Create a list of station groups
        station_groups = [
            StationGroup(
                group=group.group,
                stations=[
                    station
                    for station in station_list
                    if station.code in group.station_codes
                ],
            )
            for group in self.body.station_groups
        ]

        # Create a list of operation types and their corresponding durations
        self.operations = [
            (
                "".join(c for c in segment if c.isalpha()),
                int("".join(c for c in segment if c.isdigit())),
            )
            for segment in self.body.configuration.duration_string.split(";")
        ]

        # Initialize current time and check time interval
        next_check_time = time.time()
        check_time_interval = 1.0

        # current_operation_index = 0
        normal_operation_loop_index = 0

        inbound_advance_orders = {}
        outbound_advance_orders = {}

        is_all_orders_completed = True
        is_normal_operation_ending = False

        total_simulation_duration = sum(operation[1] for operation in self.operations)

        # Main loop that runs until the stop request is made or the simulation duration
        # is reached
        while (
            not self.status["stop_requested"]
            and time.time() <= simulation_start_time + total_simulation_duration
        ):
            loop_start_time = time.time()

            current_operation, current_operation_index = self._get_current_operation()
            current_operation_type, current_operation_duration = current_operation

            # Advance order
            if (
                current_operation_type == "AO"
                and is_all_orders_completed
                and loop_start_time >= next_check_time
            ):
                self._log("Advance order starts")

                remaining_duration = max(
                    simulation_start_time
                    + self._get_duration_up_to_current_operation(
                        current_operation_index
                    )
                    - time.time(),
                    1,
                )

                # Find the bins to be called for advance orders
                number_of_inbound_orders_for_AO = math.ceil(
                    self.body.parameters.inbound_orders_per_hour
                    * (remaining_duration / 3600)
                )
                number_of_outbound_orders_for_AO = math.ceil(
                    self.body.parameters.outbound_orders_per_hour
                    * (remaining_duration / 3600)
                )

                self._log(
                    f"Number of inbound advance orders: {number_of_inbound_orders_for_AO}"
                )
                new_inbound_advance_orders = self._create_advance_orders(
                    number_of_orders=number_of_inbound_orders_for_AO,
                    number_of_bins_per_order=self.body.parameters.inbound_bins_per_order,
                )

                self._log(
                    f"Number of outbound advance orders: {number_of_outbound_orders_for_AO}"
                )
                new_outbound_advance_orders = self._create_advance_orders(
                    number_of_orders=number_of_outbound_orders_for_AO,
                    number_of_bins_per_order=self.body.parameters.outbound_bins_per_order,
                )

                # Submit advance orders to SM
                new_orders = new_inbound_advance_orders | new_outbound_advance_orders
                if len(new_orders) > 0:
                    self._submit_advance_orders(orders=new_orders)

                # Update the advance orders
                inbound_advance_orders |= new_inbound_advance_orders
                outbound_advance_orders |= new_outbound_advance_orders

                next_check_time = (
                    simulation_start_time
                    + self._get_duration_up_to_current_operation(
                        current_operation_index
                    )
                )

                self._log(
                    f"Advance order ends in {int(next_check_time - time.time())} seconds"
                )

            # Normal operation
            elif (
                current_operation_type == "N" or not is_all_orders_completed
            ) and loop_start_time >= next_check_time:
                if normal_operation_loop_index == 0 and current_operation_type == "N":
                    normal_operation_start_time = loop_start_time
                    is_normal_operation_ending = False
                    self._log("Normal operation starts")

                # for station in station_list:
                for station_group in station_groups:
                    advance_orders = (
                        inbound_advance_orders
                        if station_group.type == "I"
                        else outbound_advance_orders
                    )

                    is_all_stations_in_group_empty = all(
                        len(station.bins) == 0 for station in station_group.stations
                    )

                    if is_all_stations_in_group_empty and current_operation_type == "N":
                        number_of_stations_in_group = len(station_group.stations)

                        # If there are advance orders for the group, assign the bins to
                        # the stations on an equal basis
                        if len(advance_orders) > 0:

                            # Get the first advance order from the dictionary
                            order_name = next(iter(advance_orders))
                            order_to_share = advance_orders[order_name]
                            number_of_bins_per_station = math.ceil(
                                len(order_to_share) / number_of_stations_in_group
                            )

                            for station in station_group.stations:
                                station.bins = order_to_share[
                                    :number_of_bins_per_station
                                ]
                                order_to_share = order_to_share[
                                    number_of_bins_per_station:
                                ]
                                station.advance_order_name = order_name

                            advance_orders.pop(order_name)

                        # If there are no more bins for the station, find new bins and call
                        # them from the matrix
                        else:
                            number_of_bins = self._get_number_of_bins_per_order(
                                station_type=station_group.type
                            )

                            number_of_bins_per_station = math.ceil(
                                number_of_bins / number_of_stations_in_group
                            )

                            remaining_bins = number_of_bins
                            for station in station_group.stations:
                                station.bins = self._get_bins_from_order(
                                    number_of_bins=min(
                                        remaining_bins, number_of_bins_per_station
                                    ),
                                    station_code=station.code,
                                )
                                station.advance_order_name = None

                                remaining_bins = max(
                                    0, remaining_bins - number_of_bins_per_station
                                )

                        # Call bins from matrix to the station
                        for station in station_group.stations:
                            bin_ids = [bin["code"] for bin in station.bins]
                            _ = self._call_bins(
                                station_code=station.code,
                                bin_ids=bin_ids,
                                advance_order_name=station.advance_order_name,
                            )

                    # During advance order operation but with remaining normal operation
                    # orders, we don't need to check station status. We just skip until
                    # all orders from all stations are completed.
                    if all(
                        len(station.bins) == 0 for station in station_group.stations
                    ):
                        continue

                    # Check station status at intervals to see if a bin is at station
                    for station in station_group.stations:
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
                            and time.time() >= station.next_job_time
                        ):
                            # Store the bin at station back to matrix
                            bin_id = status_with_bin_at_station["code"]
                            _ = self._store_bin(
                                station_code=station.code,
                                bin_id=bin_id,
                                advance_order_name=station.advance_order_name,
                            )
                            self._log(
                                f"Bin stored",
                                station_code=station.code,
                                bin_code=bin_id,
                            )

                            # Add delay to the next job time
                            delay = (
                                self.body.parameters.inbound_time
                                if station.type == "I"
                                else self.body.parameters.outbound_time
                            )
                            station.next_job_time = time.time() + delay

                            # Remove the stored bin from the list of bins assigned to the
                            # station
                            bin_to_remove = next(
                                (bin for bin in station.bins if bin["code"] == bin_id),
                                None,
                            )

                            # Sanity check: this should never happen
                            if bin_to_remove is None:
                                raise SimulationBackendException(
                                    f"Bin {bin_id} not found at station {station.code}"
                                )

                            station.bins.remove(bin_to_remove)

                next_check_time = loop_start_time + check_time_interval
                normal_operation_loop_index += (
                    1 if not is_normal_operation_ending else 0
                )

                is_all_orders_completed = (
                    all(len(station.bins) == 0 for station in station_list)
                    and current_operation_type != "N"
                )

                if is_all_orders_completed:
                    self._log("All orders completed beyond normal operation.")

                if (
                    time.time()
                    >= normal_operation_start_time + current_operation_duration
                    and not is_normal_operation_ending
                ):
                    normal_operation_loop_index = 0
                    self._log(
                        "Normal operation ends. Completing remaining bins in existing "
                        + "orders."
                    )
                    is_normal_operation_ending = True

            # Sleep for 0.5 seconds to avoid busy-waiting
            time.sleep(0.5)

        # Create the last log entry to indicate the end of the simulation
        simulation_end_time = time.time()
        self.status["stop_time"] = simulation_end_time
        self._log("Simulation ends", timestamp=simulation_end_time)

        # Update the simulation run end timestamp
        self.simulation_database.update_simulation_run_timestamp(
            simulation_run_id=self.simulation_run_id,
            end_timestamp=simulation_end_time,
        )

        # Close the simulation database connection
        self.simulation_database.close_connection()

        # Stop TC to effectively stop everything
        _ = self._tc_stop()

    def _get_current_operation(self) -> Tuple[Tuple[str, int], int]:
        current_time_in_simulation = time.time() - self.simulation_start_time

        cumulative_duration = 0
        for i, operation in enumerate(self.operations):
            cumulative_duration += operation[1]
            if current_time_in_simulation < cumulative_duration:
                return operation, i

        return self.operations[-1], len(self.operations) - 1

    def _get_duration_up_to_current_operation(
        self, current_operation_index: int
    ) -> int:
        return sum(self.operations[i][1] for i in range(current_operation_index + 1))

    def _create_advance_orders(
        self, number_of_orders: int, number_of_bins_per_order: int
    ) -> Dict[str, List[Dict[str, Any]]]:

        orders = {
            str(numpy.random.randint(1, 1000000000)): self._get_bins_from_order(
                number_of_bins=number_of_bins_per_order
            )
            for _ in range(number_of_orders)
        }

        return orders

    def _submit_advance_orders(self, orders: Dict[str, List[Dict[str, Any]]]):
        for order_name, order in orders.items():
            storages = [{"code": bin["code"]} for bin in order]
            self._send_request(
                url=f"{self.SM_BASE}/v3/advanced-orders/upsert",
                method="POST",
                data={
                    "orderNo": order_name,
                    "storages": storages,
                },
            )

            bin_ids = [bin["code"] for bin in order]
            self._log(
                f"Advance order {order_name} submitted. {len(bin_ids)} bins. "
                + f"Bin IDs: {bin_ids}"
            )
            time.sleep(1)

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
        max_retries: int = 20,
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
        max_retries : int, optional
            The maximum number of retries to get bins. Defaults to 20.

        Returns
        -------
        List[Dict[str, Any]]
            The list of bins

        Raises
        ------
        SimulationBackendException
            - If there is no bin after querying the layers
        """
        if number_of_bins < 1:
            self._log(f"No bins created for order.")
            return []

        # Use pareto probabilities as weights to randomly sample layer indices
        weights = numpy.array(self.body.parameters.pareto_probabilities)
        weights = weights / weights.sum()

        retry_count = 0
        while retry_count < max_retries:
            layer_indices = numpy.random.choice(
                len(weights), size=number_of_bins, p=weights
            )

            # Count occurrences of each layer index
            number_of_bins_per_layer = [
                int(numpy.sum(layer_indices == i)) for i in range(len(weights))
            ]
            self._log(
                f"Number of bins per layer to be assigned: {number_of_bins_per_layer}",
                station_code=station_code,
            )

            # Get bins from each layer
            bins = []
            for i, quantity in enumerate(number_of_bins_per_layer):
                if quantity > 0:
                    bins_in_this_layer = self._get_bins_from_layers(
                        min_layer=i + 1,
                        max_layer=i + 1,
                        station_code=station_code,
                    )
                    quantity_to_sample = min(quantity, len(bins_in_this_layer))
                    # Randomly sample bins from this layer
                    if quantity_to_sample > 0:
                        sampled_indices = numpy.random.choice(
                            len(bins_in_this_layer),
                            size=quantity_to_sample,
                            replace=False,
                        )
                        sampled_bins = [bins_in_this_layer[i] for i in sampled_indices]
                        bins.extend(sampled_bins)

                    time.sleep(delay)

            if len(bins) > 0:
                break

            self._log(
                f"No bins at all. Retry loop {retry_count}", station_code=station_code
            )
            retry_count += 1

        if len(bins) == 0:
            error = (
                f"No bins available after {max_retries} retries. Either they are "
                + "physically unavailable, or API is down."
            )
            self._log(f"ERROR - {error}", station_code=station_code)
            raise SimulationBackendException(error)

        # Make sure the bin codes are unique. Only keep the first occurrence of each bin.
        unique_bins = []
        unique_bin_codes = set()
        for bin in bins:
            if bin["code"] not in unique_bin_codes:
                unique_bins.append(bin)
                unique_bin_codes.add(bin["code"])

        return unique_bins

    def _get_bins_from_layers(
        self,
        min_layer: int,
        max_layer: int,
        quantity: int | None = None,
        station_code: int | None = None,
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
        station_code : int, optional
            The code of the station to append the bin call to. Defaults to None.

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
            self._log(
                f"No bins available in layers ({min_layer}, {max_layer})",
                station_code=station_code,
            )
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

    def _call_bins(
        self,
        station_code: int,
        bin_ids: List[int],
        advance_order_name: str | None = None,
    ) -> Dict[str, Any]:
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
        log_msg = (
            ""
            if advance_order_name is None
            else f"Advance order {advance_order_name}. "
        )
        log_msg += f"{len(bin_ids)} bins called. Bin IDs: {bin_ids}"

        self._log(log_msg, station_code=station_code)
        response = self._send_request(
            url=f"{self.SM_BASE}/v3/operations/call",
            method="POST",
            data={"station": station_code, "storages": bin_ids},
        )
        return response.json()

    def _store_bin(
        self, station_code: int, bin_id: int, advance_order_name: str = None
    ) -> Dict[str, Any]:
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
        data = {"station": station_code, "storage": bin_id}
        if advance_order_name is not None:
            data["advancedOrdersToComplete"] = [advance_order_name]

        response = self._send_request(
            url=f"{self.SM_BASE}/v3/operations/store",
            method="POST",
            data=data,
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

    def _log(
        self,
        log_message: str,
        station_code: int | None = None,
        bin_code: int | None = None,
        timestamp: float | None = None,
    ):
        self.simulation_database.log_action(
            timestamp=timestamp if timestamp is not None else time.time(),
            simulation_run_id=self.simulation_run_id,
            station_code=station_code,
            bin_code=bin_code,
            action=log_message,
        )

        utc8_tz = timezone(timedelta(hours=8))
        timestamp_dt = datetime.fromtimestamp(
            timestamp if timestamp is not None else time.time(), tz=utc8_tz
        )
        readable_timestamp = timestamp_dt.strftime("%Y-%m-%d %H:%M:%S")

        station_msg = f" - station={station_code}" if station_code is not None else ""
        bin_msg = f" - bin={bin_code}" if bin_code is not None else ""
        print(f"{readable_timestamp}{station_msg}{bin_msg} - {log_message}")

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
