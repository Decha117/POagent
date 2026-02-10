from __future__ import annotations

import json
from pathlib import Path
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..models import Job
from ..schemas import ConfirmPayload, UploadResponse, from_job_record
from ..services.job_runner import event_bus, job_runner
from ..services.logger import append_job_log

router = APIRouter()


def _safe_filename(name: str) -> str:
    return Path(name).name.replace(" ", "_")


@router.post("/upload", response_model=UploadResponse)
async def upload_po(
    user_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail="Unsupported file extension")

    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large")
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    job_id = str(uuid.uuid4())
    folder = settings.uploads_dir / job_id
    folder.mkdir(parents=True, exist_ok=True)

    file_path = folder / _safe_filename(file.filename)
    with file_path.open("wb") as f:
        f.write(content)

    job = Job(
        id=job_id,
        user_id=user_id,
        status="queued",
        file_path=str(file_path),
        original_filename=file.filename,
    )
    db.add(job)
    db.commit()

    append_job_log(db, job_id, "queued", "job created and queued")
    await job_runner.enqueue(job_id)
    relative_path = file_path.relative_to(settings.uploads_dir)
    return UploadResponse(job_id=job_id, status="queued", file_url=f"/uploads/{relative_path.as_posix()}")


@router.get("/job/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return from_job_record(job)


@router.get("/job/{job_id}/logs")
def get_job_logs(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    log_path = settings.job_logs_dir / f"{job_id}.log"
    if not log_path.exists():
        return {"job_id": job_id, "logs": []}
    lines = log_path.read_text(encoding="utf-8").splitlines()
    return {"job_id": job_id, "logs": lines}


@router.get("/job/{job_id}/stream")
async def job_stream(job_id: str):
    async def event_gen():
        q = event_bus.subscribe(job_id)
        try:
            while True:
                payload = await q.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            event_bus.unsubscribe(job_id, q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/job/{job_id}/confirm")
async def confirm_job(job_id: str, payload: ConfirmPayload, db: Session = Depends(get_db)):
    from ..services.job_runner import job_runner
    from ..models import PORecord

    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.extracted_fields:
        raise HTTPException(status_code=400, detail="job not ready")

    data = payload.extracted_fields.model_dump() if payload.extracted_fields else job.extracted_fields
    await job_runner._save_record(db, job, data)

    append_job_log(db, job_id, "saving", "user confirmed and data saved")
    return {"job_id": job_id, "status": "saved", "saved": db.query(PORecord).filter(PORecord.job_id == job_id).count() == 1}
