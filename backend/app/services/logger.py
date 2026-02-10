from datetime import datetime
from pathlib import Path
import logging
from sqlalchemy.orm import Session
from ..config import settings
from ..models import JobLog

settings.job_logs_dir.mkdir(parents=True, exist_ok=True)

system_logger = logging.getLogger("po_system")
if not system_logger.handlers:
    handler = logging.FileHandler(settings.storage_dir / "system.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    system_logger.addHandler(handler)
    system_logger.setLevel(logging.INFO)


def append_job_log(db: Session, job_id: str, step: str, message: str):
    log = JobLog(job_id=job_id, step=step, message=message)
    db.add(log)
    db.commit()

    line = f"{datetime.utcnow().isoformat()} | {step} | {message}\n"
    p = Path(settings.job_logs_dir / f"{job_id}.log")
    with p.open("a", encoding="utf-8") as f:
        f.write(line)

    system_logger.info("job=%s step=%s message=%s", job_id, step, message)
