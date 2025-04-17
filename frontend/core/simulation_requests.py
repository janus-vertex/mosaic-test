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
    ) -> Tuple[bool, bool | None, bool | None, str | None]:
        try:
            tc_response = MosaicRequest.send_request(
                url=f"{TC_base}/operation/healthcheck", method="GET", timeout=1
            )
            tc_real_response = json.loads(tc_response.text)
            is_healthy = True
            is_simulation_running = tc_real_response["model"]["cycle_stop"]["status"]
            is_simulation_completed = (
                tc_real_response["model"]["num_of_jobs"] == 0
                and tc_real_response["model"]["num_of_processing_jobs"] == 0
            )
            simulation_id = MosaicRequest._convert_timestamp(
                original_timestamp=tc_real_response["model"]["cycle_stop"]["updated_at"]
            )

            return (
                is_healthy,
                is_simulation_running,
                is_simulation_completed,
                simulation_id,
            )

        except requests.exceptions.RequestException as _:
            is_healthy = False
            return is_healthy, None, None, None

    @staticmethod
    def general_check(
        TC_base: str, SM_base: str
    ) -> Tuple[bool, bool | None, bool | None, str | None]:
        is_sm_healthy = MosaicRequest.SM_health_check(SM_base)
        is_tc_healthy, is_simulation_running, is_simulation_completed, simulation_id = (
            MosaicRequest.TC_status_check(TC_base)
        )
        is_healthy = is_sm_healthy and is_tc_healthy

        return is_healthy, is_simulation_running, is_simulation_completed, simulation_id

    @staticmethod
    def health_check(TC_base: str, SM_base: str) -> bool | None:
        try:
            tc_response = MosaicRequest.send_request(
                url=f"{TC_base}/operation/healthcheck", method="GET", timeout=1
            )
            tc_real_response = json.loads(tc_response.text)

            sm_response = MosaicRequest.send_request(
                url=f"{SM_base}/v3/settings/OrderDispatcher", method="GET", timeout=1
            )
            sm_real_response = json.loads(sm_response.text)
            return (
                tc_real_response["model"]["cycle_stop"]["status"]
                and sm_real_response["data"]["value"][Parameters.ZONE_NAME]["isActive"]
            )

        except requests.exceptions.RequestException as _:
            return None

    @staticmethod
    def stop(TC_base: str) -> requests.Response | None:
        try:
            response = MosaicRequest.send_request(
                url=f"{TC_base}/operation/cyclestop",
                data={
                    "status": "Enabled",
                    "reason": "Matrix simulation has stopped the simulation.",
                },
            )
            streamlit.success("Simulation stopped successfully.", icon="✅")
            return response
        except requests.exceptions.RequestException as _:
            streamlit.warning(
                "Failed to stop simulation, or there is no simulation to be stopped.",
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
