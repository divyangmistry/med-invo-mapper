"""
main.py — Agent entry point.

Startup sequence
----------------
1. Configure logging
2. Ensure runtime directories exist
3. Initialise database
4. Verify Ollama is reachable and the configured model is available
5. Start the capture loop (drop-folder or live camera)
6. For each captured image: extract → DB log → Excel append
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config import Config
from database import init_db, log_transaction
from extractor import ExtractionError, extract_from_image
from excel_writer import append_to_excel
from capture import start_capture


# ─── Logging Setup ───────────────────────────────────────────────────────────

def _setup_logging() -> None:
    Config.ensure_dirs()
    log_file = Config.LOG_DIR / f"agent_{datetime.now().strftime('%Y-%m-%d')}.log"

    fmt = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
        format=fmt,
        handlers=handlers,
    )
    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "watchdog", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ─── Ollama Health Check ──────────────────────────────────────────────────────

def _wait_for_ollama(max_wait: int = 120) -> None:
    """
    Poll Ollama until it responds or max_wait seconds have elapsed.
    Exits the process on timeout (Docker will restart the container).
    """
    url = f"{Config.OLLAMA_BASE_URL}/api/tags"
    logger.info("Waiting for Ollama at %s …", Config.OLLAMA_BASE_URL)
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=5)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                logger.info("Ollama is ready. Available models: %s", models)
                if not any(Config.VLM_MODEL in m for m in models):
                    logger.warning(
                        "Model '%s' not found in Ollama. "
                        "Run: docker exec med_ollama ollama pull %s",
                        Config.VLM_MODEL, Config.VLM_MODEL,
                    )
                return
        except Exception:
            pass
        logger.debug("Ollama not ready yet — retrying in 5s …")
        time.sleep(5)

    logger.critical("Ollama did not respond within %ds. Exiting.", max_wait)
    sys.exit(1)


# ─── Per-Image Processing Pipeline ───────────────────────────────────────────

def _process_image(image_path: Path) -> None:
    """
    Full pipeline for a single captured/dropped image:
      extract → DB log → Excel append
    """
    logger.info("━" * 60)
    logger.info("Processing: %s", image_path.name)

    confidence_flag = "OK"

    try:
        # 1. VLM Extraction
        result = extract_from_image(image_path, enhance=True)
        confidence_flag = result.confidence_flag
        logger.info(
            "Extracted: vendor=%r  invoice=%r  items_count=%d  flag=%s",
            result.vendor_name, result.invoice_number, 
            len(result.items), confidence_flag,
        )

    except ExtractionError as exc:
        logger.error("Extraction failed: %s", exc)
        # Log a placeholder transaction so the event is auditable
        result_dict = {
            "vendor_name": "EXTRACTION_FAILED",
            "invoice_number": "N/A",
            "items": [{
                "medicine_name": "N/A",
                "medicine_code": "N/A",
                "batch_number": "N/A",
                "manufacturing_date": "N/A",
                "expiry_date": "N/A",
                "quantity": 0,
            }]
        }
        log_transaction(result_dict, confidence_flag="MANUAL_REVIEW",
                        source_image=image_path.name)
        return

    # 2. DB Logging
    try:
        txns = log_transaction(
            result.to_dict(),
            confidence_flag=confidence_flag,
            source_image=image_path.name,
        )
        logger.info("DB transactions saved: count=%d", len(txns))
    except Exception as exc:
        logger.error("DB write failed: %s", exc)

    # 3. Excel Append
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        excel_path = append_to_excel(result, timestamp=ts, source_image=image_path.name)
        logger.info("Excel updated: %s", excel_path.name)
    except Exception as exc:
        logger.error("Excel write failed: %s", exc)

    logger.info("Done: %s", image_path.name)


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    _setup_logging()

    logger.info("=" * 60)
    logger.info("  Medical Invoice & Label Extraction Agent")
    logger.info("  Started: %s", datetime.now(timezone.utc).isoformat())
    logger.info("  Config : %s", Config.summary())
    logger.info("=" * 60)

    # Initialise database
    init_db()

    # Wait for Ollama to be ready
    _wait_for_ollama(max_wait=120)

    # Start capture loop (blocks)
    logger.info("Starting capture loop in %s mode …", Config.CAMERA_MODE.upper())
    start_capture(on_image=_process_image)


if __name__ == "__main__":
    main()
