from typing import List

from pydantic import BaseModel


class Configuration(BaseModel):
    name: str
    start_time: str
    duration_in_seconds: int
    server_number: int


class Station(BaseModel):
    code: int
    type: str


class Parameters(BaseModel):
    pick_time: int
    goods_in_time: int
    pick_throughput: int
    goods_in_throughput: int
    pareto_probabilities: List[float]


class JobsCreationRequest(BaseModel):
    parameters: Parameters
    configuration: Configuration
    stations: List[Station]
