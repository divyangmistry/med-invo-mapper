# Testing Guide — Med-Invo Mapper

## Testing Phases

Run tests in this exact order. Each phase builds on the previous one.

---

## Phase 1 — Unit Tests (No Docker, no GPU needed)

Install deps once in a local Python venv:

```powershell
# From the project root
python -m venv .venv
.venv\Scripts\activate
pip install -r agent\requirements.txt
```

### 1a. Database Test

```powershell
python tests\test_database.py
```

**Expected output:**
```
  ✅  ALL 12 DATABASE TESTS PASSED
```

### 1b. Excel Writer Test

```powershell
python tests\test_excel.py
```

**Expected output:**
```
  ✅  ALL 9 EXCEL TESTS PASSED
```

---

## Phase 2 — AI Extraction Test (Requires Ollama)

### Step 1: Start Ollama only

```powershell
# Copy dev env file
copy .env.dev .env

# Start only Ollama (not the full stack)
docker compose up -d ollama

# Wait ~30s, then pull the model (one-time, ~4.5 GB)
docker exec med_ollama ollama pull qwen2-vl:7b

# Verify
docker exec med_ollama ollama list
```

### Step 2: Drop your test image

Place your invoice + label image here:
```
tests\sample_images\test_invoice.jpg
```

> If you don't have a real image yet, use any clear, well-lit photo of a printed invoice. The system will tell you which fields were or weren't extracted.

### Step 3: Run extractor test

```powershell
python tests\test_extractor.py --image tests\sample_images\test_invoice.jpg
```

**Expected output (example):**
```
  vendor_name           : Cipla Ltd.
  invoice_number        : INV-2024-001
  medicine_name         : Azithromycin 500mg
  medicine_code         : AZM500
  batch_number          : B20240301
  manufacturing_date    : 03/2024
  expiry_date           : 03/2026
  confidence_flag       : OK

  ✅  ALL 5 EXTRACTOR TESTS PASSED
```

> If some fields show `UNKNOWN`, that's normal — it means they weren't clearly visible in the image. The agent will flag those rows as `MANUAL_REVIEW` in Excel.

---

## Phase 3 — End-to-End Drop-Folder Test (Full Docker stack)

```powershell
# Start everything
docker compose up -d

# Check all containers are healthy
docker compose ps

# Drop your test image into the inputs folder
copy tests\sample_images\test_invoice.jpg inputs\

# Watch processing in real-time
docker logs -f med_agent

# Verify output Excel file was created
dir outputs\

# Open the Excel file
start outputs\Inventory_2026-03-17.xlsx

# Open analytics dashboard
start http://localhost:8501
```

---

## Phase 4 — Camera Integration Test (Run NATIVELY on Windows — not in Docker)

> Run this **after** Phase 3 is working. This verifies OpenCV can talk to your USB camera before enabling live mode.

```powershell
# Install opencv-python (native, not headless — so the preview window works)
pip install opencv-python numpy

# Run camera test
python tests\test_camera.py --index 0

# If camera not found at index 0, try:
python tests\test_camera.py --index 1
```

**What happens:**
- 6 automated checks run (open, resolution, frame read, MOG2, snapshot save)
- A **10-second live preview window** opens so you can verify framing
- If all pass, the script prints the exact `.env.prod` values to use

**Expected output:**
```
  ✅  ALL 6 CAMERA TESTS PASSED

  📌  Next step: Update .env.prod with:
          CAMERA_MODE=live
          CAMERA_INDEX=0
          CAPTURE_WIDTH=1920
          CAPTURE_HEIGHT=1080
```

After passing, update `.env.prod` and test the live stack:

```powershell
copy .env.prod .env
docker compose up -d
```

---

## Quick Reference

| Phase | Script | Requires |
|---|---|---|
| 1a — DB | `python tests\test_database.py` | Python + deps only |
| 1b — Excel | `python tests\test_excel.py` | Python + deps only |
| 2 — Extractor | `python tests\test_extractor.py` | Ollama + model pulled |
| 3 — E2E | Drop file into `inputs\` | Full Docker stack |
| 4 — Camera | `python tests\test_camera.py` | Native Windows + USB cam |
