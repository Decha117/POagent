# Local PO OCR Web App (Thai PO)

โปรเจคนี้เป็น Web Application แบบ Local/Offline สำหรับอัปโหลดรูปใบ PO ภาษาไทย → ทำ OCR → parse/validate → ให้ผู้ใช้แก้ไข → ยืนยันบันทึกลงฐานข้อมูล

## 1) สรุปสถาปัตยกรรม (สั้น กระชับ)
- **FastAPI (Backend)**: จัดการ upload, queue, OCR pipeline, validation, persistence
- **Frontend (Vanilla JS + SSE)**: แสดงสถานะและ log แบบเรียลไทม์ + ฟอร์มแก้ไขผล OCR
- **SQLite**: เหมาะกับเครื่องเดียว (Local) และย้ายไป PostgreSQL ได้ในอนาคต
- **In-process Queue**: ใช้ `asyncio.Queue` + worker จำกัดจำนวน (`WORKER_COUNT=1` default) เพื่อไม่ให้เว็บค้างบน Mac i5 / RAM 8GB
- **OCR Engine Strategy**:
  - `typhoon` mode: ทำ local inference จริงด้วยโมเดล Typhoon OCR 1.5 2B (ผ่าน `transformers`)
  - `fast` mode: โหมดเบา ลดทรัพยากร (preprocess + OCR fallback)

## 2) โครงสร้างโปรเจค

```text
backend/
  app/
    api/routes.py
    services/
      job_runner.py
      ocr.py
      preprocess.py
      logger.py
    config.py
    database.py
    main.py
    models.py
    schemas.py
frontend/
  index.html
  app.js
  styles.css
scripts/
  run.sh
models/
  (วาง Typhoon OCR local model)
docs/
  architecture.md
.env.example
pyproject.toml
```

## 3) API Endpoints
- `POST /upload` -> upload PO image + create queued job
- `GET /job/{id}` -> status + result
- `GET /job/{id}/logs` -> log history
- `GET /job/{id}/stream` -> SSE realtime status/log
- `POST /job/{id}/confirm` -> user confirm before save

## 4) Validation Rules
- ใช้ Pydantic schema (`ExtractedFields`, `POItem`)
- วันที่ (`po_date`) ต้องเป็น ISO (`YYYY-MM-DD`)
- ตัวเลข parse เป็น `float`
- ตรวจความสอดคล้อง `sum(line_total)` กับ `sub_total` (tolerance ±5)
- ส่งคืนผลลัพธ์ในรูป JSON ที่มี:
  - `extracted_fields`
  - `confidence`
  - `warnings`
  - `raw_text`

## 5) วิธีติดตั้งและรัน (macOS Local)

### 5.1 เตรียม Python env
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

> ถ้าต้องใช้ OCR จริงผ่าน pytesseract:
> - ติดตั้ง tesseract ในเครื่อง (เช่น `brew install tesseract tesseract-lang`)

> ถ้าต้องใช้ `OCR_MODE=typhoon`:
> - ต้องมี PyTorch + Transformers (กำหนดไว้แล้วใน `pyproject.toml`)
> - ตั้ง `TYPHOON_MODEL_PATH` เป็นชื่อโมเดลบน Hugging Face (ค่า default คือ `typhoon-ai/typhoon-ocr1.5-2b`) หรือ path local ก็ได้

### 5.2 ตั้งค่า env
```bash
cp .env.example .env
```

ตัวอย่างค่า:
```env
APP_NAME=Local PO OCR
MAX_UPLOAD_MB=8
OCR_MODE=fast
WORKER_COUNT=1
AUTO_SAVE=false
TYPHOON_MODEL_PATH=typhoon-ai/typhoon-ocr1.5-2b
```

### 5.3 Run แบบ 1 บรรทัด
```bash
./scripts/run.sh
```

เปิดเว็บ: `http://localhost:8000`

## 6) Typhoon OCR 1.5 2B และ fallback
- สำหรับเครื่อง MacBook Pro 13" 2019 (Intel i5, RAM 8GB):
  - เริ่มด้วย `OCR_MODE=fast`
  - ใช้ `WORKER_COUNT=1`
  - จำกัดไฟล์ไม่เกิน 8MB
  - ทำ preprocess แบบลด resolution เพื่อประหยัด RAM/CPU
- เมื่อจะใช้ `OCR_MODE=typhoon`:
  - ตั้ง `TYPHOON_MODEL_PATH=typhoon-ai/typhoon-ocr1.5-2b` (หรือระบุ path local ของโมเดล)
  - ระบบจะโหลดโมเดลผ่าน `transformers` จาก Hugging Face อัตโนมัติเมื่อไม่ใช่ path local
  - หาก dependency ไม่ครบ / inference ล้มเหลว จะ fallback ไป `fast` อัตโนมัติพร้อมบันทึก note

## 7) ข้อจำกัดและ tuning บน Mac i5/8GB
- ควรประมวลผลทีละงาน (`WORKER_COUNT=1`) เพื่อเลี่ยง CPU spike
- หลีกเลี่ยงรูปความละเอียดสูงเกินจำเป็น (resize ใน preprocess แล้ว)
- ถ้างานเยอะ:
  - เพิ่มคิว (ยังไม่เพิ่ม worker)
  - ตั้ง cron/maintenance ลบไฟล์เก่าใน `storage/uploads`

## 8) Logging และ Security ขั้นพื้นฐาน
- แยก log รายงานต่อ job: `storage/job_logs/{job_id}.log`
- system log รวม: `storage/system.log`
- ตรวจ extension + จำกัดขนาดไฟล์ + กัน empty file
- sanitize filename และเก็บไฟล์แยกโฟลเดอร์ต่อ `job_id`
- ป้องกัน overwrite โดยใช้ UUID job_id

## 9) Workflow ที่รองรับแล้ว
1. ผู้ใช้กรอก `user_id`
2. อัปโหลด JPG/PNG
3. ระบบ preprocess ภาพ
4. ส่งเข้า queue แล้ว background OCR
5. หน้าเว็บแสดงสถานะ (queued / processing / extracting / validating / saving / done / failed) + live logs ผ่าน SSE
6. OCR result แสดงใน text area (แก้ไขได้)
7. กด Confirm เพื่อบันทึก DB
