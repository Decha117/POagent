# Architecture (Local-first)

- **Backend**: FastAPI + SQLite + SQLAlchemy.
- **Queue**: in-process `asyncio.Queue` + single worker by default (`WORKER_COUNT=1`) to protect Mac i5/8GB from overload.
- **OCR**:
  - `OCR_MODE=typhoon`: Typhoon OCR 1.5 2B inference via Transformers แบบ local-only (`local_files_only=True`) โดย `TYPHOON_MODEL_PATH` ต้องชี้ไปที่โฟลเดอร์โมเดลในเครื่อง และจะรายงาน error ทันทีเมื่อ inference ไม่สำเร็จ (ไม่มี fallback).
  - `OCR_MODE=fast`: lower-resource path (optionally pytesseract, else deterministic fallback) for reliability.
- **Realtime**: SSE endpoint (`/job/{id}/stream`) pushes status/log events.
- **Storage**: `storage/uploads/{job_id}` for files, `storage/job_logs/{job_id}.log` for per-job logs, `storage/system.log` for system logs.
- **Human-in-the-loop**: result stays editable on UI; save to DB only when `/confirm` is called (or enable `AUTO_SAVE=true`).
