"""
test_extractor.py — Integration test for the VLM extraction pipeline.

REQUIRES: Ollama running with qwen2-vl:7b pulled.
          Either run this after `docker compose up -d ollama`
          OR if Ollama is installed locally point OLLAMA_BASE_URL to localhost.

Usage
-----
    # With Docker Ollama running:
    python tests/test_extractor.py --image tests/sample_images/test_invoice.png

    # With a specific Ollama URL:
    python tests/test_extractor.py --image path/to/img.png --ollama http://localhost:11434

What it tests
-------------
  ✓ Ollama server is reachable
  ✓ Configured model is available
  ✓ Image can be encoded and sent to VLM
  ✓ VLM returns valid JSON
  ✓ JSON parses into ExtractionResult
  ✓ At least vendor_name or medicine_name is populated (non-UNKNOWN)
"""
import argparse
import os
import sys
from pathlib import Path

# ── CLI args ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="VLM extraction integration test")
parser.add_argument(
    "--image", "-i",
    type=str,
    default=str(Path(__file__).parent / "sample_images" / "test_invoice.png"),
    help="Path to test invoice/label image (default: tests/sample_images/test_invoice.png)",
)
parser.add_argument(
    "--ollama",
    type=str,
    default=None,
    help="Ollama base URL (default: from .env or http://localhost:11434)",
)
parser.add_argument(
    "--model",
    type=str,
    default=None,
    help="Model name (default: from .env or qwen2-vl:7b)",
)
args = parser.parse_args()

# Set env before importing agent modules
if args.ollama:
    os.environ["OLLAMA_BASE_URL"] = args.ollama
if args.model:
    os.environ["VLM_MODEL"] = args.model

os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("VLM_MODEL", "llava:7b")
# os.environ.setdefault("VLM_MODEL", "qwen2-vl:7b")
os.environ.setdefault("DATABASE_URL", "sqlite://")  # Not used here but imported
os.environ.setdefault("OUTPUT_DIR", "/tmp")
os.environ.setdefault("INPUT_DIR", "/tmp")
os.environ.setdefault("LOG_DIR", "/tmp")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

import httpx
from config import Config

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"
results = []


def check(name: str, condition: bool, detail: str = "") -> None:
    icon = PASS if condition else FAIL
    msg = f"  {icon}  {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append(condition)


print("\n" + "=" * 60)
print("  Med-Invo Mapper — Extractor Integration Test")
print(f"  Model  : {Config.VLM_MODEL}")
print(f"  Ollama : {Config.OLLAMA_BASE_URL}")
print(f"  Image  : {args.image}")
print("=" * 60)

# ── Test 1: Ollama reachability ───────────────────────────────
print("\n[1/5] Ollama server reachability")
try:
    resp = httpx.get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=10)
    check("Ollama responds with 200", resp.status_code == 200,
          f"status={resp.status_code}")
    available_models = [m["name"] for m in resp.json().get("models", [])]
    print(f"         Available models: {available_models}")
except Exception as e:
    check("Ollama responds with 200", False, str(e))
    print("\n  ⚠️  Cannot reach Ollama. Make sure it is running:")
    print("       docker compose --env-file .env.dev up -d ollama")
    print("       docker exec med_ollama ollama pull qwen2-vl:7b\n")
    sys.exit(1)

# ── Test 2: Model is pulled ────────────────────────────────────
print("\n[2/5] Model availability")
model_available = any(Config.VLM_MODEL in m for m in available_models)
check(f"Model '{Config.VLM_MODEL}' is pulled", model_available,
      "Run: docker exec med_ollama ollama pull " + Config.VLM_MODEL if not model_available else "")

if not model_available:
    print(f"\n  ⚠️  Pull the model first: docker exec med_ollama ollama pull {Config.VLM_MODEL}")
    sys.exit(1)

# ── Test 3: Image file exists ─────────────────────────────────
print("\n[3/5] Image file check")
image_path = Path(args.image)
check("Image file exists", image_path.exists(), str(image_path))
if not image_path.exists():
    print(f"\n  ⚠️  Place a test image at: {image_path}")
    print("       You can also generate a mock one: python tests/generate_mock_image.py")
    sys.exit(1)

# ── Test 4: Extraction runs without exception ─────────────────
print("\n[4/5] VLM extraction pipeline")
from extractor import extract_from_image, ExtractionResult

result: ExtractionResult | None = None
try:
    print("       Sending image to VLM … (this may take 30–90s on first run)")
    result = extract_from_image(image_path, enhance=True)
    check("Extraction completed without exception", True)
    check("Result is ExtractionResult instance", isinstance(result, ExtractionResult))
except Exception as e:
    check("Extraction completed without exception", False, str(e))

# ── Test 5: Field quality check ──────────────────────────────
print("\n[5/5] Extracted field quality")
if result:
    print("\n  ── Raw Extraction Result ──────────────────────────────")
    for k, v in result.to_dict().items():
        print(f"     {k:<22}: {v}")
    print("  ────────────────────────────────────────────────────────")

    has_vendor = result.vendor_name not in ("UNKNOWN", "", None)
    has_medicine = result.medicine_name not in ("UNKNOWN", "", None)
    has_expiry = result.expiry_date not in ("UNKNOWN", "", None)

    check("vendor_name extracted", has_vendor, result.vendor_name)
    check("medicine_name extracted", has_medicine, result.medicine_name)
    check("expiry_date extracted", has_expiry, result.expiry_date)
    check("confidence_flag is set", result.confidence_flag in ("OK", "MANUAL_REVIEW"))
else:
    for _ in range(4):
        results.append(False)

# ── Summary ───────────────────────────────────────────────────
passed = sum(results)
total = len(results)
print("\n" + "=" * 60)
if passed == total:
    print(f"  ✅  ALL {total} EXTRACTOR TESTS PASSED")
elif passed >= total - 1:
    print(f"  ⚠️   {passed}/{total} PASSED — some fields were UNKNOWN (check image quality)")
else:
    print(f"  ❌  {total - passed} / {total} TESTS FAILED")
print("=" * 60 + "\n")
sys.exit(0 if passed >= total - 1 else 1)
