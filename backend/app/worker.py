import asyncio

from .database import Base, engine
from .services.job_runner import job_runner


async def run_worker() -> None:
    Base.metadata.create_all(bind=engine)
    await job_runner.start_db_polling_workers()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run_worker())
