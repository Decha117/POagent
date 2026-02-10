from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="queued", nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    field_confidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    logs: Mapped[list["JobLog"]] = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    step: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[Job] = relationship("Job", back_populates="logs")


class PORecord(Base):
    __tablename__ = "po_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True)
    po_number: Mapped[str | None] = mapped_column(String, nullable=True)
    po_date: Mapped[str | None] = mapped_column(String, nullable=True)
    buyer_company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    buyer_tax_id: Mapped[str | None] = mapped_column(String, nullable=True)
    seller_company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    seller_tax_id: Mapped[str | None] = mapped_column(String, nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    vat_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    vat_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    grand_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="THB")
    payment_terms: Mapped[str | None] = mapped_column(String, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
