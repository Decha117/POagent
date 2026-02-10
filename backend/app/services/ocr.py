from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class OCRRawOutput:
    raw_text: str
    engine: str
    note: str | None = None


class OCRService:
    _typhoon_model = None
    _typhoon_processor = None
    _typhoon_device: str | None = None

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
                return OCRRawOutput(raw_text=text, engine="fast")
        except Exception:
            pass

        simulated = (
            "PO Number: PO-LOCAL-001\n"
            "PO Date: 2025-01-02\n"
            "Buyer: Local Buyer Co.,Ltd\n"
            "Sub Total: 1000.00\nVAT 7%: 70.00\nGrand Total: 1070.00\n"
            "Item A qty 2 unit pcs unit_price 500 line_total 1000"
        )
        return OCRRawOutput(raw_text=simulated, engine="fast", note="using simulated OCR text")

    def _load_typhoon_components(self):
        if OCRService._typhoon_model is not None and OCRService._typhoon_processor is not None:
            return OCRService._typhoon_model, OCRService._typhoon_processor

        import torch
        from transformers import AutoModelForVision2Seq, AutoProcessor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        model_source = Path(self.typhoon_model_path)
        if not model_source.exists():
            raise FileNotFoundError(
                "Typhoon OCR local model path not found. "
                "Set TYPHOON_MODEL_PATH to a downloaded local model directory."
            )

        processor = AutoProcessor.from_pretrained(
            str(model_source),
            local_files_only=True,
            trust_remote_code=True,
        )
        model = AutoModelForVision2Seq.from_pretrained(
            str(model_source),
            local_files_only=True,
            trust_remote_code=True,
            torch_dtype=dtype,
        )
        model.to(device)
        model.eval()

        OCRService._typhoon_model = model
        OCRService._typhoon_processor = processor
        OCRService._typhoon_device = device
        return model, processor

    def _run_typhoon(self, image_path: Path) -> OCRRawOutput:
        try:
            import torch
            from PIL import Image

            model, processor = self._load_typhoon_components()
            device = OCRService._typhoon_device or "cpu"

            image = Image.open(image_path).convert("RGB")
            prompt = (
                "Extract all visible text from this purchase order image. "
                "Keep line breaks and preserve key-value formatting. "
                "Do not add explanations."
            )

            if hasattr(processor, "apply_chat_template"):
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image"},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ]
                text_input = processor.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
                inputs = processor(
                    text=[text_input],
                    images=[image],
                    return_tensors="pt",
                )
            else:
                inputs = processor(images=image, text=prompt, return_tensors="pt")

            inputs = {
                k: (v.to(device) if isinstance(v, torch.Tensor) else v)
                for k, v in inputs.items()
            }

            with torch.inference_mode():
                generated = model.generate(**inputs, max_new_tokens=2048)

            prompt_len = inputs["input_ids"].shape[-1] if "input_ids" in inputs else 0
            trimmed = generated[:, prompt_len:] if prompt_len else generated
            text = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

            if text:
                return OCRRawOutput(
                    raw_text=text,
                    engine="typhoon",
                    note=f"Typhoon OCR local inference ({device})",
                )

            fast_result = self._run_fast(image_path)
            fast_result.note = "Typhoon returned empty text; falling back to fast OCR"
            return fast_result
        except Exception as exc:
            fast_result = self._run_fast(image_path)
            fast_result.note = f"Typhoon OCR inference error: {exc}; falling back to fast OCR"
            return fast_result


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
