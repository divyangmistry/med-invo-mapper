"""
extractor.py — VLM-based data extraction from invoice/label images.

Flow
----
1. Encode image as base64.
2. POST to Ollama /api/chat with a vision-compatible message payload.
   (Uses /api/chat — required by qwen2.5vl, qwen2-vl, llava:13b and all modern VLMs.)
3. Parse the LLM text response into an ExtractionResult Pydantic model.
4. Validate logical consistency (non-empty required fields).
5. If critical fields are missing, retry up to MAX_RETRIES times.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import httpx
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from pydantic import BaseModel, Field, field_validator
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed
from typing import List

from config import Config

logger = logging.getLogger(__name__)

# ─── Pydantic Result Model ────────────────────────────────────────────────────

class MedicineItem(BaseModel):
    """A single medicine entry from an invoice."""
    medicine_name: str = Field(default="UNKNOWN", description="Full medicine / drug name")
    medicine_code: str = Field(default="UNKNOWN", description="Short medicine code or SKU")
    batch_number: str = Field(default="UNKNOWN", description="Batch or lot number")
    manufacturing_date: str = Field(default="UNKNOWN", description="Mfg date, format MM/YYYY or YYYY-MM")
    expiry_date: str = Field(default="UNKNOWN", description="Expiry date, format MM/YYYY or YYYY-MM")
    quantity: int = Field(default=1, ge=0)
    # ── Financial / invoice line-item fields ──
    unit: str = Field(default="UNKNOWN", description="Pack size or unit")
    free_quantity: int = Field(default=0, ge=0, description="Free goods quantity")
    mrp: str = Field(default="UNKNOWN", description="Maximum retail price")
    ptr: str = Field(default="UNKNOWN", description="Price to retailer")
    discount_percent: str = Field(default="UNKNOWN", description="Discount percentage")
    discount_amount: str = Field(default="UNKNOWN", description="Discount amount")
    base_amount: str = Field(default="UNKNOWN", description="Taxable / base amount")
    gst_percent: str = Field(default="UNKNOWN", description="GST rate percentage")
    amount: str = Field(default="UNKNOWN", description="Line total after tax")
    hsn_code: str = Field(default="UNKNOWN", description="HSN / SAC code")
    location: str = Field(default="UNKNOWN", description="Storage location")

    @field_validator("medicine_code", mode="before")
    @classmethod
    def normalise_code(cls, v: str) -> str:
        return str(v).strip().upper() if v else "UNKNOWN"

    @property
    def critical_fields_present(self) -> bool:
        required = [self.medicine_name, self.batch_number, self.expiry_date]
        return all(f not in ("UNKNOWN", "", None) for f in required)


class ExtractionResult(BaseModel):
    """Structured output from the VLM extraction containing multiple items."""
    vendor_name: str = Field(default="UNKNOWN", description="Vendor / supplier name from invoice")
    invoice_number: str = Field(default="UNKNOWN", description="Invoice or bill number")
    items: List[MedicineItem] = Field(default_factory=list, description="List of medicines found")
    confidence_flag: str = Field(default="OK")  # OK | MANUAL_REVIEW
    # ── Invoice header fields ──
    bill_date: str = Field(default="UNKNOWN", description="Bill date from invoice")
    entry_date: str = Field(default="UNKNOWN", description="Entry date")
    entry_number: str = Field(default="UNKNOWN", description="Entry number")
    tax_type: str = Field(default="UNKNOWN", description="Tax type, e.g. SGST/UGST")
    payment_type: str = Field(default="UNKNOWN", description="Credit or Cash")
    pan_number: str = Field(default="UNKNOWN", description="PAN number")
    # ── Invoice totals ──
    total_base: str = Field(default="UNKNOWN", description="Total taxable/base amount")
    sgst_amount: str = Field(default="UNKNOWN", description="SGST amount")
    cgst_amount: str = Field(default="UNKNOWN", description="CGST amount")
    igst_amount: str = Field(default="UNKNOWN", description="IGST amount")
    cess_amount: str = Field(default="UNKNOWN", description="Cess amount")
    discount_total: str = Field(default="UNKNOWN", description="Total discount")
    total_amount: str = Field(default="UNKNOWN", description="Grand total")
    other_charges: str = Field(default="UNKNOWN", description="Other charges +/-")
    credit_note: str = Field(default="UNKNOWN", description="Credit note amount")
    tcs_value: str = Field(default="UNKNOWN", description="TCS value")

    @property
    def critical_fields_present(self) -> bool:
        basic = self.vendor_name not in ("UNKNOWN", "", None) and \
                self.invoice_number not in ("UNKNOWN", "", None)
        if not basic or not self.items:
            return False
        return all(item.critical_fields_present for item in self.items)

    def to_dict(self) -> dict:
        return self.model_dump()


class ExtractionError(Exception):
    """Raised when extraction fails after all retries."""


# ─── Prompt Template ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a precision OCR engine. Extract pharmaceutical data from images.
Rules:
1. Output ONLY valid JSON.
2. Keep values short. No long strings of numbers unless they are explicitly written.
3. If text is blurry or not found, use "UNKNOWN".
4. Do NOT use markdown. Start with { and end with }.
"""

EXTRACTION_PROMPT = """\
Image contains: Pharmaceutical Invoice + Medicine Strip.
OCR Text Layer (for reference/hint only):
\"\"\"
{ocr_text}
\"\"\"

Extract all medicine entries AND invoice header details into this JSON schema:
{{
  "vendor_name": "string (Party / supplier name)",
  "invoice_number": "string (Bill No)",
  "bill_date": "string (Bill Dt, DD/MM/YYYY)",
  "entry_date": "string (Entry Dt, DD/MM/YYYY)",
  "entry_number": "string (Entry No)",
  "tax_type": "string (e.g. RD within state - SGST/UGST)",
  "payment_type": "string (Credit or Cash)",
  "pan_number": "string (PAN)",
  "total_base": "string (Base total amount)",
  "sgst_amount": "string (SGST amount)",
  "cgst_amount": "string (CGST amount)",
  "igst_amount": "string (IGST amount)",
  "cess_amount": "string (Cess amount)",
  "discount_total": "string (Total discount)",
  "total_amount": "string (Grand total)",
  "other_charges": "string (Other +/- charges)",
  "credit_note": "string (Credit note amount)",
  "tcs_value": "string (TCS value)",
  "items": [
    {{
      "medicine_name": "string (Item Name)",
      "medicine_code": "string (Short code or SKU)",
      "batch_number": "string (Batch)",
      "manufacturing_date": "MM/YYYY",
      "expiry_date": "MM/YYYY",
      "quantity": 1,
      "unit": "string (Unit / pack size)",
      "free_quantity": 0,
      "mrp": "string (MRP)",
      "ptr": "string (PTR / Price to Retailer)",
      "discount_percent": "string (D%)",
      "discount_amount": "string (Disc)",
      "base_amount": "string (BASE / taxable amount)",
      "gst_percent": "string (Gst%)",
      "amount": "string (Amount / line total)",
      "hsn_code": "string (HSN code)",
      "location": "string (Location/Locat.)"
    }}
  ]
}}
IMPORTANT: Extract EVERY medicine entry found in the invoice. If there are 5 medicines, there must be 5 items in the list.
The base_amount in items is the taxable amount (BASE column). If not explicitly present, use the amount before tax.
Example Invoice Number: 'INV-123'
Result:"""


# ─── Image Helpers ───────────────────────────────────────────────────────────

def _encode_image_to_base64(image_path: Path) -> str:
    """Read image file and return base64-encoded string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _enhance_image(image_path: Path) -> Path:
    """
    Apply basic preprocessing to improve OCR accuracy:
    - Increase contrast
    - Sharpen edges
    Returns path to a temp enhanced file saved in /tmp/ (NOT in the watched inputs/ dir).
    """
    import tempfile
    # IMPORTANT: save to system temp dir, NOT image_path.parent.
    # If saved inside inputs/, the folder watcher will pick it up as a new file.
    tmp_dir = Path(tempfile.gettempdir())
    tmp_path = tmp_dir / f"med_enhanced_{image_path.name}"
    img = Image.open(image_path).convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=2))
    img.save(tmp_path, quality=95)
    return tmp_path


def _run_tesseract_ocr(image_path: Path) -> str:
    """Perform OCR on the image using Tesseract."""
    try:
        # We use lang='eng' by default, can be expanded to 'osd' for orientation
        text = pytesseract.image_to_string(Image.open(image_path))
        return text.strip()
    except Exception as e:
        logger.warning("Tesseract OCR failed: %s", e)
        return ""


def _parse_json_from_text(text: str) -> dict:
    """
    Robustly extract JSON from LLM response text.
    Handles markdown fences and attempts to fix common truncation issues.
    """
    def _strip_fences(s: str) -> str:
        s = s.strip()
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
        return s.strip()

    def _basic_repairs(s: str) -> str:
        """
        Apply safe, local repairs that keep semantics:
        - balance braces
        - close dangling quote
        - convert missing values (`"key":,` / `"key":}`) to null
        - remove trailing commas before } or ]
        """
        # Balance braces (common when model truncates)
        open_braces = s.count("{")
        close_braces = s.count("}")
        if open_braces > close_braces:
            logger.debug(
                "Attempting to repair truncated JSON (braces: %d vs %d)",
                open_braces,
                close_braces,
            )
            if s.count('"') % 2 != 0:
                s += '"'
            s += "}" * (open_braces - close_braces)

        # Fix missing values like:  "ptr": ,   or  "ptr": }
        # Replace with null while preserving delimiter.
        s = re.sub(r'("(?:(?:\\.)|[^"\\])*"\s*:\s*)(?=(,|\}|\]))', r"\1null", s)

        # Remove trailing commas before object/array close
        s = re.sub(r",\s*(\}|\])", r"\1", s)
        return s

    # Strip markdown fences if present
    text = _strip_fences(text)

    # Find first { ... } block
    # If the model cuts off, we might have { but no matching }
    start_idx = text.find("{")
    if start_idx == -1:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
    
    # Prefer the broadest {...} span to avoid leading chatter.
    json_text = text[start_idx:]
    last_close = json_text.rfind("}")
    if last_close != -1:
        json_text = json_text[: last_close + 1]

    candidates: list[str] = []
    # 1) as-is (after fence stripping and trimming)
    candidates.append(json_text)
    # 2) safe repairs
    candidates.append(_basic_repairs(json_text))
    # 3) regex-extracted object (can remove trailing non-json)
    match = re.search(r"\{.*\}", json_text, re.DOTALL)
    if match:
        candidates.append(_basic_repairs(match.group()))

    last_err: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except Exception as e:
            last_err = e

    raise ValueError(f"Could not parse or repair JSON: {text[:200]!r}") from last_err


# ─── Core Extraction ─────────────────────────────────────────────────────────

def _call_ollama(image_b64: str, prompt: str) -> str:
    """
    Send image + prompt to local Ollama via the /api/chat endpoint.
    Uses the chat format which is compatible with ALL Ollama vision models
    (qwen2.5vl, qwen2-vl, llava:7b, llava:13b, etc.).
    """
    url = f"{Config.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": Config.VLM_MODEL,
        "stream": False,
        "options": {
            "temperature": Config.VLM_TEMPERATURE,
            "num_predict": 1024,
        },
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            },
        ],
    }
    logger.debug("Calling Ollama chat: model=%s url=%s", Config.VLM_MODEL, url)
    start = time.time()
    with httpx.Client(timeout=Config.VLM_TIMEOUT) as client:
        response = client.post(url, json=payload)
        if not response.is_success:
            # Log full error details to make debugging easier
            logger.error(
                "Ollama HTTP %d: %s",
                response.status_code,
                response.text[:500],
            )
            response.raise_for_status()
    elapsed = time.time() - start
    # /api/chat returns: {"message": {"role": "assistant", "content": "..."}}
    result = response.json().get("message", {}).get("content", "")
    logger.debug("Ollama responded in %.1fs: %s...", elapsed, result[:80])
    return result


def _should_retry_ollama_error(exc: Exception) -> bool:
    """
    Only retry on transient transport/gateway errors.
    Do NOT retry on HTTP 500 model crashes (e.g. GGML_ASSERT) because it will
    just loop and spam the server with the same request.
    """
    if isinstance(exc, (httpx.TimeoutException, httpx.RequestError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else None
        return status in (408, 429, 502, 503, 504)
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    retry=retry_if_exception(_should_retry_ollama_error),
)
def _call_ollama_with_retry(image_b64: str, prompt: str) -> str:
    return _call_ollama(image_b64, prompt)


def extract_from_image(
    image_path: Path | str,
    enhance: bool = True,
) -> ExtractionResult:
    """
    Full extraction pipeline for a single image.

    Parameters
    ----------
    image_path : str or Path  — path to the invoice/label image
    enhance    : bool          — apply contrast/sharpness preprocessing

    Returns
    -------
    ExtractionResult — validated structured extraction result

    Raises
    ------
    ExtractionError — if all retries are exhausted with no valid result
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    logger.info("Starting extraction: %s", image_path.name)

    # Preprocess
    work_path = _enhance_image(image_path) if enhance else image_path
    image_b64 = _encode_image_to_base64(work_path)
    ocr_text = _run_tesseract_ocr(work_path)

    # First pass
    attempts = 0
    result: Optional[ExtractionResult] = None
    last_error: Optional[Exception] = None

    while attempts <= Config.MAX_RETRIES:
        attempts += 1
        try:
            # Inject OCR text into prompt
            prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)
            
            raw_text = _call_ollama_with_retry(image_b64, prompt)
            # Detailed log of raw response for troubleshooting
            logger.debug("--- RAW LLM RESPONSE START ---\n%s\n--- RAW LLM RESPONSE END ---", raw_text)
            parsed = _parse_json_from_text(raw_text)
            result = ExtractionResult(**parsed)

            if result.critical_fields_present:
                logger.info("Extraction successful on attempt %d (found %d items)", 
                            attempts, len(result.items))
                break
            else:
                logger.warning("Attempt %d: missing critical fields or items — retrying", attempts)
                if attempts <= Config.MAX_RETRIES and Config.RETRY_ON_MISSING_FIELDS:
                    # On retry, could potentially try different enhancement, but keeping it simple for now
                    pass

        except Exception as exc:
            last_error = exc
            logger.warning("Attempt %d failed: %s", attempts, exc)

    # Clean up temp file
    if enhance and work_path != image_path and work_path.exists():
        work_path.unlink(missing_ok=True)

    if result is None:
        raise ExtractionError(
            f"All {Config.MAX_RETRIES + 1} attempts failed. Last error: {last_error}"
        )

    # Set confidence based on completeness
    if not result.critical_fields_present:
        result.confidence_flag = "MANUAL_REVIEW"
        logger.warning("Extraction complete but some critical fields are UNKNOWN or no items found — flagged MANUAL_REVIEW")

    return result
