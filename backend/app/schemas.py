from __future__ import annotations

from datetime import date
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator


class POItem(BaseModel):
    description: str = ""
    quantity: float = 0
    unit: str | None = None
    unit_price: float = 0
    line_total: float = 0


class ExtractedFields(BaseModel):
    po_number: str | None = None
    po_date: str | None = None
    buyer_company_name: str | None = None
    buyer_tax_id: str | None = None
    seller_company_name: str | None = None
    seller_tax_id: str | None = None
    delivery_address: str | None = None
    items: list[POItem] = Field(default_factory=list)
    sub_total: float | None = None
    vat_rate: float | None = None
    vat_amount: float | None = None
    grand_total: float | None = None
    currency: str = "THB"
    payment_terms: str | None = None

    @field_validator("po_date")
    @classmethod
    def validate_date(cls, value: str | None):
        if value is None:
            return value
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def validate_totals(self):
        if self.sub_total is not None and self.items:
            sum_lines = sum(item.line_total for item in self.items)
            if abs(sum_lines - self.sub_total) > 5:
                raise ValueError(f"line_total sum ({sum_lines}) does not match sub_total ({self.sub_total})")
        return self


class OCRResult(BaseModel):
    extracted_fields: ExtractedFields
    confidence: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    raw_text: str


class JobResponse(BaseModel):
    id: str
    status: str
    progress_percent: int
    user_id: str
    original_filename: str
    created_at: str
    updated_at: str
    last_message: str | None = None
    error_message: str | None = None
    result: OCRResult | None = None


class ConfirmPayload(BaseModel):
    extracted_fields: ExtractedFields | None = None
    auto_save: bool = False


class LogLine(BaseModel):
    ts: str
    step: str
    message: str


class UploadResponse(BaseModel):
    job_id: str
    status: str
    file_url: str


def from_job_record(job: Any) -> JobResponse:
    progress_by_status = {
        "queued": 5,
        "processing": 20,
        "extracting": 55,
        "validating": 80,
        "saving": 92,
        "done": 100,
        "failed": 100,
    }
    last_log = job.logs[-1].message if getattr(job, "logs", None) else None
    result = None
    if job.extracted_fields:
        result = OCRResult(
            extracted_fields=ExtractedFields(**job.extracted_fields),
            confidence=job.field_confidence or {},
            warnings=job.warnings or [],
            raw_text=job.raw_ocr_text or "",
        )
    return JobResponse(
        id=job.id,
        status=job.status,
        progress_percent=progress_by_status.get(job.status, 0),
        user_id=job.user_id,
        original_filename=job.original_filename,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        last_message=last_log,
        error_message=job.error_message,
        result=result,
    )
