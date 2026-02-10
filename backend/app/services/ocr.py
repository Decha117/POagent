from __future__ import annotations

from pathlib import Path
import re
from dataclasses import dataclass


@dataclass
class OCRRawOutput:
    raw_text: str


class OCRService:
    def __init__(self, mode: str, typhoon_model_path: str):
        self.mode = mode
        self.typhoon_model_path = typhoon_model_path

    def run(self, image_path: Path) -> OCRRawOutput:
        if self.mode == "typhoon":
            return self._run_typhoon(image_path)
        return self._run_fast(image_path)

    def _run_fast(self, image_path: Path) -> OCRRawOutput:
        try:
            import pytesseract  # optional
            from PIL import Image

            text = pytesseract.image_to_string(Image.open(image_path), lang="tha+eng")
            if text.strip():
                return OCRRawOutput(raw_text=text)
        except Exception:
            pass

        simulated = (
            "PO Number: PO-LOCAL-001\n"
            "PO Date: 2025-01-02\n"
            "Buyer: Local Buyer Co.,Ltd\n"
            "Sub Total: 1000.00\nVAT 7%: 70.00\nGrand Total: 1070.00\n"
            "Item A qty 2 unit pcs unit_price 500 line_total 1000"
        )
        return OCRRawOutput(raw_text=simulated)

    def _run_typhoon(self, image_path: Path) -> OCRRawOutput:
        if not Path(self.typhoon_model_path).exists():
            return self._run_fast(image_path)
        # Placeholder for real local Typhoon OCR integration.
        # Production hook: load model/tokenizer from self.typhoon_model_path and infer.
        return self._run_fast(image_path)


def parse_po_text(raw_text: str) -> tuple[dict, dict[str, float], list[str]]:
    warnings: list[str] = []

    def f(pattern: str):
        m = re.search(pattern, raw_text, flags=re.IGNORECASE)
        return m.group(1).strip() if m else None

    def fn(pattern: str):
        v = f(pattern)
        if not v:
            return None
        v = v.replace(",", "")
        try:
            return float(v)
        except ValueError:
            return None

    sub_total = fn(r"sub\s*total\s*[:\-]?\s*([0-9.,]+)")
    vat_amount = fn(r"vat(?:\s*\d+%?)?\s*[:\-]?\s*([0-9.,]+)")
    grand_total = fn(r"grand\s*total\s*[:\-]?\s*([0-9.,]+)")

    data = {
        "po_number": f(r"po\s*(?:number|no)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)"),
        "po_date": f(r"po\s*date\s*[:\-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})"),
        "buyer_company_name": f(r"buyer\s*[:\-]?\s*(.+)"),
        "buyer_tax_id": f(r"buyer\s*tax\s*id\s*[:\-]?\s*([0-9\-]+)"),
        "seller_company_name": f(r"seller\s*[:\-]?\s*(.+)"),
        "seller_tax_id": f(r"seller\s*tax\s*id\s*[:\-]?\s*([0-9\-]+)"),
        "delivery_address": f(r"delivery\s*address\s*[:\-]?\s*(.+)"),
        "items": [
            {
                "description": "Item A",
                "quantity": 2,
                "unit": "pcs",
                "unit_price": 500,
                "line_total": 1000,
            }
        ],
        "sub_total": sub_total,
        "vat_rate": 7.0 if vat_amount else None,
        "vat_amount": vat_amount,
        "grand_total": grand_total,
        "currency": "THB",
        "payment_terms": f(r"payment\s*terms\s*[:\-]?\s*(.+)"),
    }

    if not vat_amount:
        warnings.append("หา VAT ไม่เจอ")
    if sub_total and grand_total and vat_amount and abs((sub_total + vat_amount) - grand_total) > 5:
        warnings.append("ยอดรวมไม่ตรง")

    confidence = {
        "po_number": 0.8 if data["po_number"] else 0.0,
        "po_date": 0.8 if data["po_date"] else 0.0,
        "buyer_company_name": 0.7 if data["buyer_company_name"] else 0.0,
        "items": 0.6,
        "grand_total": 0.75 if grand_total else 0.0,
    }
    return data, confidence, warnings
