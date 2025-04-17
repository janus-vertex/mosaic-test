from datetime import datetime

from fastapi import BackgroundTasks, Body, FastAPI
from job_service import JobService
from pydantic import BaseModel

app = FastAPI()

# Add this at the top level of the file
job_creation_status = {"is_successful": False}


class JobsCreationRequest(BaseModel):
    pick_time: int
    goods_in_time: int
    pick_throughput: int
    goods_in_throughput: int
    number_of_jobs: int


@app.get("/time")
async def get_current_time():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"current_time": current_time}


@app.get("/status")
async def get_status():
    return job_creation_status


@app.post("/jobs/create")
async def create_jobs(
    background_tasks: BackgroundTasks,
    jobs_creation_request: JobsCreationRequest = Body(...),
):
    # Reset the status before starting new job creation
    job_creation_status["is_successful"] = False

    job_service = JobService(
        pick_time=jobs_creation_request.pick_time,
        goods_in_time=jobs_creation_request.goods_in_time,
        pick_throughput=jobs_creation_request.pick_throughput,
        goods_in_throughput=jobs_creation_request.goods_in_throughput,
    )

    def create_jobs_and_update_status(number_of_jobs: int):
        job_service.create_jobs(number_of_jobs=number_of_jobs)
        job_creation_status["is_successful"] = True

    background_tasks.add_task(
        create_jobs_and_update_status,
        number_of_jobs=jobs_creation_request.number_of_jobs,
    )

    return {"message": "Job creation process has been started"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
