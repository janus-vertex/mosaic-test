class JobService:
    def __init__(
        self,
        pick_time: int,
        goods_in_time: int,
        pick_throughput: int,
        goods_in_throughput: int,
    ):
        self.pick_time = pick_time
        self.goods_in_time = goods_in_time
        self.pick_throughput = pick_throughput
        self.goods_in_throughput = goods_in_throughput

    def create_jobs(self, number_of_jobs: int):
        pass
