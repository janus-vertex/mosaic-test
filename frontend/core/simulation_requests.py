import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pytz
import requests
import streamlit
from core.parameters import Parameters


class MosaicRequest:
    @staticmethod
    def SM_health_check(SM_base: str) -> bool:
        try:
            sm_response = MosaicRequest.send_request(
                url=f"{SM_base}/v3/settings/OrderDispatcher", method="GET", timeout=1
            )
            sm_real_response = json.loads(sm_response.text)
            return sm_real_response["data"]["value"][Parameters.ZONE_NAME]["isActive"]

        except requests.exceptions.RequestException as _:
            return False

    @staticmethod
    def TC_status_check(
        TC_base: str,
    ) -> Tuple[bool, bool | None]:
        try:
            tc_response = MosaicRequest.send_request(
                url=f"{TC_base}/operation/healthcheck", method="GET", timeout=1
            )
            tc_real_response = json.loads(tc_response.text)
            is_healthy = True
            is_tc_running = tc_real_response["model"]["cycle_stop"]["status"]

            return is_healthy, is_tc_running

        except requests.exceptions.RequestException as _:
            is_healthy = False
            return is_healthy, None

    @staticmethod
    def backend_status_check(
        simulation_base: str,
    ) -> Tuple[bool, bool | None, str | None]:
        try:
            response = MosaicRequest.send_request(
                url=f"{simulation_base}/status",
                method="GET",
            )
            real_response = json.loads(response.text)
            simulation_name = real_response["simulation_name"]
            is_simulation_completed = (
                True if real_response["stop_time"] is not None else False
            )
            is_healthy = True
            return is_healthy, is_simulation_completed, simulation_name
        except requests.exceptions.RequestException as _:
            is_healthy = False
            return is_healthy, None, None

    @staticmethod
    def general_check(
        TC_base: str, SM_base: str, simulation_base: str
    ) -> Tuple[bool, bool | None, bool | None, str | None]:
        is_sm_healthy = MosaicRequest.SM_health_check(SM_base)
        is_tc_healthy, is_tc_running = MosaicRequest.TC_status_check(TC_base)
        is_backend_healthy, is_simulation_completed, simulation_name = (
            MosaicRequest.backend_status_check(simulation_base)
        )

        is_healthy = is_sm_healthy and is_tc_healthy and is_backend_healthy

        return is_healthy, is_tc_running, is_simulation_completed, simulation_name

    @staticmethod
    def stop(TC_base: str, simulation_base: str) -> None:
        try:
            _ = MosaicRequest.tc_stop(TC_base)
            _ = MosaicRequest.simulation_stop(simulation_base)
            streamlit.success("Simulation stopped successfully.", icon="✅")
            return None
        except requests.exceptions.RequestException as _:
            return None

    @staticmethod
    def tc_stop(TC_base: str) -> requests.Response | None:
        try:
            response = MosaicRequest.send_request(
                url=f"{TC_base}/operation/cyclestop",
                data={
                    "status": "Enabled",
                    "reason": "Matrix simulation has stopped the simulation.",
                },
            )
            return response
        except requests.exceptions.RequestException as _:
            streamlit.warning(
                "Failed to stop TC, or there is no job queue to be stopped.",
                icon="⚠️",
            )
            return None

    @staticmethod
    def simulation_stop(simulation_base: str) -> requests.Response | None:
        try:
            response = MosaicRequest.send_request(
                url=f"{simulation_base}/jobs/stop",
                method="POST",
            )
            return response
        except requests.exceptions.RequestException as _:
            streamlit.warning(
                "Failed to stop simulation, or there is no job creation to be stopped.",
                icon="⚠️",
            )
            return None

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

    @staticmethod
    def _convert_timestamp(original_timestamp: str) -> str:
        # Parse the ISO format string to datetime
        utc_dt = datetime.fromisoformat(original_timestamp)

        # Convert to UTC+8
        utc8_tz = pytz.timezone("Asia/Singapore")
        utc8_dt = utc_dt.astimezone(utc8_tz)

        # Format the datetime as required
        return utc8_dt.strftime("%Y-%m-%d %H:%M:%S")
