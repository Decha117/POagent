from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from sqlalchemy.orm import Session
from ..config import settings
from ..database import SessionLocal
from ..models import Job, PORecord
from ..schemas import ExtractedFields
from .logger import append_job_log
from .ocr import OCRService, parse_po_text
from .preprocess import preprocess_image


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

    async def start(self):
        for _ in range(max(1, settings.worker_count)):
            self.workers.append(asyncio.create_task(self.worker_loop()))

    async def enqueue(self, job_id: str):
        await self.queue.put(job_id)

    async def worker_loop(self):
        while True:
            job_id = await self.queue.get()
            try:
                await self.process_job(job_id)
            finally:
                self.queue.task_done()

    async def _step(self, db: Session, job: Job, status: str, message: str):
        job.status = status
        db.add(job)
        db.commit()
        append_job_log(db, job.id, status, message)
        await event_bus.publish(job.id, {"status": status, "message": message})

    async def process_job(self, job_id: str):
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if not job:
                return

            await self._step(db, job, "processing", "loading and preprocessing image")
            src = Path(job.file_path)
            processed = src.parent / "processed.png"
            preprocess_image(src, processed, fast_mode=(settings.ocr_mode == "fast"))

            await self._step(db, job, "extracting", "running OCR inference")
            raw = self.ocr.run(processed)

            await self._step(db, job, "validating", "parsing + validating structured data")
            fields, confidence, warnings = parse_po_text(raw.raw_text)
            validated = ExtractedFields(**fields)

            job.raw_ocr_text = raw.raw_text
            job.extracted_fields = validated.model_dump()
            job.field_confidence = confidence
            job.warnings = warnings

            if settings.auto_save:
                await self._save_record(db, job, validated.model_dump())
                await self._step(db, job, "saving", "auto-save enabled, data persisted")

            await self._step(db, job, "done", "ocr complete")
        except Exception as exc:
            if job := db.get(Job, job_id):
                job.status = "failed"
                job.error_message = str(exc)
                db.add(job)
                db.commit()
                append_job_log(db, job.id, "failed", str(exc))
                await event_bus.publish(job.id, {"status": "failed", "message": str(exc)})
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
