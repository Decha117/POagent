# Architecture (Local-first)

- **Backend**: FastAPI + SQLite + SQLAlchemy.
- **Queue**: in-process `asyncio.Queue` + single worker by default (`WORKER_COUNT=1`) to protect Mac i5/8GB from overload.
- **OCR**:
  - `OCR_MODE=typhoon`: Typhoon OCR inference via Transformers โดยเลือกแหล่งโมเดลผ่าน `TYPHOON_MODEL_SOURCE` (`local`/`huggingface`) และกำหนด path หรือ repo id ผ่าน `TYPHOON_MODEL_REF`; กรณี Hugging Face private repo รองรับ `HF_TOKEN`. หาก inference ล้มเหลวจะรายงาน error ทันที (ไม่มี fallback).
  - `OCR_MODE=fast`: lower-resource path (optionally pytesseract, else deterministic fallback) for reliability.
- **Realtime**: SSE endpoint (`/job/{id}/stream`) pushes status/log events.
- **Storage**: `storage/uploads/{job_id}` for files, `storage/job_logs/{job_id}.log` for per-job logs, `storage/system.log` for system logs.
- **Human-in-the-loop**: result stays editable on UI; save to DB only when `/confirm` is called (or enable `AUTO_SAVE=true`).
