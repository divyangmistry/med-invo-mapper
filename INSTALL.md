# 📦 Med-Invo Mapper — Installation & Quick-Start Guide

## What You Get

| Component | What it does |
|-----------|-------------|
| **Launcher** | A single GUI window to start/stop everything |
| **AI Agent** | Watches `inputs/` for invoice images → extracts data → saves to DB & Excel |
| **Dashboard** | Streamlit web dashboard at `http://localhost:8501` |
| **Ollama + VLM** | Local AI model (qwen2.5vl:7b) — runs 100% offline |

---

## Prerequisites

| | macOS | Windows |
|--|-------|---------|
| Python | 3.10+ from [python.org](https://python.org/downloads) | 3.10+ from [python.org](https://python.org/downloads) |
| Internet | Required during setup (to download Ollama + AI model) | Required during setup |

> **Note:** After setup, the application runs **completely offline**.

---

## Step 1 — Run the Setup Script (once, on first install)

### macOS / Linux
```bash
# In a Terminal, navigate to the project folder:
cd /path/to/med-invo-mapper

# Make executable and run:
chmod +x setup.sh
./setup.sh
```

### Windows
```
Double-click setup.bat
(or right-click → Run as Administrator for best results)
```

The setup script will:
1. ✅ Check Python 3.10+
2. ✅ Install **Ollama** (the local AI runtime)
3. ✅ Download the **qwen2.5vl:7b** model (~4 GB, first time only)
4. ✅ Create a Python virtual environment (`venv/`)
5. ✅ Install all dependencies
6. ✅ Create working directories (`db/`, `inputs/`, `outputs/`, `logs/`)
7. ✅ Create `.env` configuration file

---

## Step 2 — Start the Application

### Option A — Run directly from the project folder (no build needed)
```bash
# macOS/Linux
source venv/bin/activate
python launcher/app.py
```
```bat
REM Windows
venv\Scripts\activate.bat
python launcher\app.py
```

### Option B — Build a standalone app (no Python needed on the client machine)

```bash
# macOS/Linux  →  produces dist/MedInvoMapper.app
chmod +x build_app.sh
./build_app.sh
open dist/MedInvoMapper.app
```
```bat
REM Windows  →  produces dist\MedInvoMapper\MedInvoMapper.exe
build_app.bat
dist\MedInvoMapper\MedInvoMapper.exe
```

---

## Step 3 — Using the Application

1. **Click ▶ Start** — the agent and dashboard both start
2. The dashboard opens automatically at **http://localhost:8501**
3. Drop a `.jpg` / `.png` invoice image into the **`inputs/`** folder
4. Watch the live log pane — the AI extracts data in real-time
5. The dashboard updates with each new extraction
6. **Click ■ Stop** (or close the window) to shut everything down cleanly

---

## Working Directories

| Folder | Purpose |
|--------|---------|
| `inputs/` | Drop invoice images here (JPG, PNG, BMP, TIFF) |
| `inputs/processed/` | Images moved here after processing |
| `outputs/` | Excel files — one per month |
| `db/` | SQLite database (`med_invo.db`) |
| `logs/` | Agent log files |

---

## Configuring the AI Model

Edit `.env` to change settings:

```ini
# Switch to a different model (must be pulled via Ollama first)
VLM_MODEL=llava:7b

# Enable live camera instead of folder-watch mode
CAMERA_MODE=live
CAMERA_INDEX=0       # 0 = first USB camera
```

To pull a different model:
```bash
ollama pull llava:7b
```

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| "Ollama not responding" | Run `ollama serve` in a terminal, then restart the launcher |
| "Model not found" | Run `ollama pull qwen2.5vl:7b` in a terminal |
| Dashboard not opening | Click **🌐 Open Dashboard** button or visit `http://localhost:8501` manually |
| Permission denied on setup.sh | Run `chmod +x setup.sh` first |
| Camera not detected | Check `CAMERA_INDEX=0` in `.env`, try `1` or `2` |

---

## Updating the Application

To update to a new version:
1. Replace the project files
2. Re-run `setup.sh` / `setup.bat` (it skips already-installed components)
3. Re-run `build_app.sh` / `build_app.bat` to rebuild the bundle

Your `db/`, `inputs/`, `outputs/`, and `logs/` data is **never touched** by updates.
