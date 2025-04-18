from pydantic import BaseModel


class JobsCreationRequest(BaseModel):
    pick_time: int
    goods_in_time: int
    pick_throughput: int
    goods_in_throughput: int
    number_of_jobs: int
    number_of_bins: int 


class JobService:
    def __init__(
        self,
        jobs_creation_request: JobsCreationRequest,
    ):
        self.pick_time = jobs_creation_request.pick_time
        self.goods_in_time = jobs_creation_request.goods_in_time
        self.pick_throughput = jobs_creation_request.pick_throughput
        self.goods_in_throughput = jobs_creation_request.goods_in_throughput

    def create_jobs(self, number_of_jobs: int):
        pass
