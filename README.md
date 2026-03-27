# 🏥 Med-Invo-Mapper: Local AI Medical Invoice Agent

**Med-Invo-Mapper** is a local-first AI agent designed for pharmacies and medical distributors to automate data extraction from physical invoices and medicine strips. It uses Vision Language Models (VLMs) running locally via **Ollama** to ensure 100% data privacy and offline capability.

---

## 🚀 Key Features

- **Local-First AI**: Powered by `qwen2.5vl:7b` (via Ollama). No cloud APIs, no subscription fees, 100% data privacy.
- **Smart Extraction**: Extracts Vendor Name, Invoice Number, SKU, Batch, Expiry, Quantity, MRP, and Tax details.
- **Self-Healing OCR**: Combines Tesseract OCR "hints" with VLM reasoning to reduce hallucinations.
- **Multi-Destination**: Persists data to an **SQLite database** and auto-appends to categorized **Excel files**.
- **Unified Launcher**: A simple GUI to manage the Agent and the Streamlit Dashboard.
- **Audit Ready**: Every extraction is logged with a "Confidence Flag" for easy manual review.

---

## 🛠️ Tech Stack

- **Logic**: Python 3.10+
- **Inference**: Ollama (VLM: Qwen2.5-VL / LLaVA)
- **Database**: SQLAlchemy + SQLite (WAL mode)
- **Dashboard**: Streamlit
- **Preprocessing**: PIL + Tesseract OCR

---

## 📦 Prerequisites

| Tool | Requirement | link |
|---|---|---|
| **Python** | 3.10 or 3.11 | [Download](https://www.python.org/downloads/) |
| **Ollama** | Latest version | [Download](https://ollama.com/) |
| **Tesseract** | OCR Engine | `brew install tesseract` (macOS) |

---

## ⚙️ Installation

### 1. Run the Setup Script
This script will install Python dependencies, Ollama (if missing), and pull the required AI model (~4GB).

**macOS / Linux:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
Double-click `setup.bat`.

### 2. Configure Environment
Copy `.env.local` to `.env` (the setup script does this for you) and adjust your settings:
```ini
VLM_MODEL=qwen2.5vl:7b
CAMERA_MODE=folder  # 'folder' for watching inputs/ or 'live' for USB camera
```

---

## 📖 How to Use

### Startup
The easiest way is to use the launcher:
```bash
source venv/bin/activate
python launcher/app.py
```
Click **▶ Start** to fire up both the extraction agent and the web dashboard.

### Processing Invoices
1. Drop image files (`.jpg`, `.png`) into the **`inputs/`** folder.
2. The agent detects the file, enhances it, and extracts data.
3. The image is moved to `inputs/processed/`.
4. Results appear immediately on the dashboard at `http://localhost:8501`.

### Standalone App
To build a standalone macOS `.app` or Windows `.exe`:
```bash
chmod +x build_app.sh
./build_app.sh
```
Find your app in the `dist/` directory.

---

## 🧪 Development & Testing

Run the test suite to verify your setup:
```bash
source venv/bin/activate
python -m pytest tests/
```

---

## 📄 Project Insights

For a deep dive into the architecture, technical decisions, and data flow of this project, see the [Portfolio Monologue](monologue.md).

---

## 🤝 Contributing
Feel free to open issues or submit pull requests for new features, better prompts, or bug fixes.

---
*Developed for speed, privacy, and precision in medical logistics.*
