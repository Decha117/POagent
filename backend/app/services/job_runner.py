from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import Job, PORecord
from ..schemas import ExtractedFields
from .logger import append_job_log
from .ocr import OCRService, parse_po_text


class EventBus:
    def __init__(self):
        self.subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers[job_id].append(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue):
        if job_id in self.subscribers and q in self.subscribers[job_id]:
            self.subscribers[job_id].remove(q)

    async def publish(self, job_id: str, payload: dict):
        for q in self.subscribers.get(job_id, []):
            await q.put(payload)


event_bus = EventBus()


class JobRunner:
    def __init__(self):
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.ocr = OCRService(settings.ocr_mode, settings.typhoon_model_path)
        self.workers: list[asyncio.Task] = []

    async def start_queue_workers(self):
        for _ in range(max(1, settings.worker_count)):
            self.workers.append(asyncio.create_task(self.worker_loop()))

    async def start_db_polling_workers(self):
        for _ in range(max(1, settings.worker_count)):
            self.workers.append(asyncio.create_task(self.polling_worker_loop()))

    async def enqueue(self, job_id: str):
        if settings.enable_in_process_worker:
            await self.queue.put(job_id)

    async def worker_loop(self):
        while True:
            job_id = await self.queue.get()
            try:
                await self.process_job(job_id)
            finally:
                self.queue.task_done()

    async def polling_worker_loop(self):
        while True:
            job_id = self._claim_next_queued_job()
            if job_id:
                await self.process_job(job_id)
                continue
            await asyncio.sleep(max(settings.worker_poll_interval_sec, 0.1))

    def _claim_next_queued_job(self) -> str | None:
        db = SessionLocal()
        try:
            stmt = select(Job).where(Job.status == "queued").order_by(Job.created_at.asc())
            job = db.execute(stmt).scalars().first()
            if not job:
                return None
            job.status = "processing"
            db.add(job)
            db.commit()
            return job.id
        finally:
            db.close()

    async def _step(self, db: Session, job: Job, status: str, message: str, extra: dict | None = None):
        progress_by_status = {
            "queued": 5,
            "processing": 20,
            "extracting": 55,
            "validating": 80,
            "saving": 92,
            "done": 100,
            "failed": 100,
        }
        job.status = status
        db.add(job)
        db.commit()
        append_job_log(db, job.id, status, message)
        payload = {
            "status": status,
            "message": message,
            "progress_percent": progress_by_status.get(status, 0),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            payload.update(extra)
        await event_bus.publish(job.id, payload)

    async def process_job(self, job_id: str):
        db = SessionLocal()
        overall_start = asyncio.get_running_loop().time()
        try:
            job = db.get(Job, job_id)
            if not job:
                return

            if job.status != "processing":
                await self._step(db, job, "processing", "loading uploaded image")
            src = Path(job.file_path)

            await self._step(db, job, "extracting", "running OCR inference")
            ocr_started = asyncio.get_running_loop().time()
            raw = self.ocr.run(src)
            ocr_ms = int((asyncio.get_running_loop().time() - ocr_started) * 1000)
            append_job_log(db, job.id, "extracting", f"ocr engine={raw.engine}")
            append_job_log(db, job.id, "extracting", f"ocr duration_ms={ocr_ms}")
            if raw.note:
                append_job_log(db, job.id, "extracting", raw.note)

            await self._step(db, job, "validating", "parsing + validating structured data")
            fields, confidence, warnings = parse_po_text(raw.raw_text)
            validated = ExtractedFields(**fields)

            if raw.note:
                warnings = [raw.note, *warnings]

            job.raw_ocr_text = raw.raw_text
            job.extracted_fields = validated.model_dump()
            job.field_confidence = confidence
            job.warnings = warnings

            if settings.auto_save:
                await self._save_record(db, job, validated.model_dump())
                await self._step(db, job, "saving", "auto-save enabled, data persisted")

            total_ms = int((asyncio.get_running_loop().time() - overall_start) * 1000)
            await self._step(
                db,
                job,
                "done",
                "ocr complete",
                extra={"engine": raw.engine, "ocr_duration_ms": ocr_ms, "total_duration_ms": total_ms},
            )
        except Exception as exc:
            if job := db.get(Job, job_id):
                job.error_message = str(exc)
                db.add(job)
                db.commit()
                await self._step(db, job, "failed", str(exc))
        finally:
            db.close()

    async def _save_record(self, db: Session, job: Job, data: dict):
        exists = db.query(PORecord).filter(PORecord.job_id == job.id).first()
        if exists:
            exists.data = data
            db.add(exists)
            db.commit()
            return

        rec = PORecord(
            job_id=job.id,
            po_number=data.get("po_number"),
            po_date=data.get("po_date"),
            buyer_company_name=data.get("buyer_company_name"),
            buyer_tax_id=data.get("buyer_tax_id"),
            seller_company_name=data.get("seller_company_name"),
            seller_tax_id=data.get("seller_tax_id"),
            delivery_address=data.get("delivery_address"),
            sub_total=data.get("sub_total"),
            vat_rate=data.get("vat_rate"),
            vat_amount=data.get("vat_amount"),
            grand_total=data.get("grand_total"),
            currency=data.get("currency") or "THB",
            payment_terms=data.get("payment_terms"),
            data=data,
        )
        db.add(rec)
        db.commit()


job_runner = JobRunner()
