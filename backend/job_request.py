from typing import List

from pydantic import BaseModel


class Configuration(BaseModel):
    id: int
    name: str
    server_number: int
    duration_string: str


class Station(BaseModel):
    code: int
    type: str


class Parameters(BaseModel):
    inbound_time: int
    outbound_time: int
    inbound_bins_per_order: int
    outbound_bins_per_order: int
    inbound_orders_per_hour: int
    outbound_orders_per_hour: int
    pareto_probabilities: List[float]


class StationGroup(BaseModel):
    group: int
    station_codes: List[int]


class JobsCreationRequest(BaseModel):
    parameters: Parameters
    configuration: Configuration
    stations: List[Station]
    station_groups: List[StationGroup]
