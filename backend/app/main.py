from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .api.routes import router
from .config import settings
from .database import Base, engine
from .services.job_runner import job_runner


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

frontend_dir = Path("frontend")
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.on_event("startup")
async def startup_event():
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.job_logs_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    await job_runner.start()
