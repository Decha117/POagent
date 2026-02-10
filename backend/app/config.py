from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Local PO OCR"
    storage_dir: Path = Path("storage")
    uploads_dir: Path = Path("storage/uploads")
    job_logs_dir: Path = Path("storage/job_logs")
    sqlite_path: Path = Path("storage/app.db")
    max_upload_mb: int = 8
    allowed_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png")
    worker_count: int = 1
    enable_in_process_worker: bool = True
    worker_poll_interval_sec: float = 1.0
    auto_save: bool = False
    ocr_mode: str = "fast"  # fast | typhoon
    typhoon_model_source: str = "local"  # local | huggingface
    typhoon_model_ref: str = "models/typhoon-ocr1.5-2b"
    hf_token: str | None = None


settings = Settings()
