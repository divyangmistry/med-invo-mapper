# Autonomous Medical Invoice & Label Extraction Agent
## Prerequisites, Setup & Deployment Guide

> **Version:** 1.0 | **Date:** 2026-03-17 | **Platform:** Windows 10/11 or Ubuntu 22.04 LTS

---

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Host Machine Setup](#2-host-machine-setup)
3. [Project Structure](#3-project-structure)
4. [Configuration Files](#4-configuration-files)
5. [Docker Compose Deployment](#5-docker-compose-deployment)
6. [Model Download & Verification](#6-model-download--verification)
7. [First-Run Validation](#7-first-run-validation)
8. [Operational Runbook](#8-operational-runbook)
9. [Auto-Start on Boot](#9-auto-start-on-boot)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

### 1.1 Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| **CPU** | 8-core (Intel i7 / Ryzen 7) | 16-core (i9 / Ryzen 9 / Threadripper) |
| **RAM** | 32 GB | 64 GB |
| **GPU** | Nvidia RTX 3090 (24 GB VRAM) | Nvidia RTX 4090 (24 GB VRAM) |
| **Storage** | 512 GB NVMe SSD | 1 TB NVMe SSD |
| **Camera** | 1080p USB webcam | 4K webcam (Logitech Brio 4K) |
| **OS** | Windows 10/11 (64-bit) or Ubuntu 22.04 LTS | Ubuntu 22.04 / 24.04 LTS |

> [!IMPORTANT]
> A dedicated Nvidia GPU with **CUDA 12.x** support is mandatory for local VLM inference at acceptable speeds. CPU-only inference is functional but will be 10–30× slower.

### 1.2 Software Prerequisites

Ensure the following are installed **before** proceeding:

| Software | Version | Download |
|---|---|---|
| **Docker Desktop** (Windows) **or** Docker Engine (Linux) | 24.x+ | https://docs.docker.com/get-docker |
| **Docker Compose** | v2.x (bundled with Docker Desktop) | Bundled |
| **Nvidia GPU Driver** | 535.x+ (CUDA 12.x) | https://www.nvidia.com/Download/index.aspx |
| **Nvidia Container Toolkit** | Latest | https://docs.nvidia.com/datacenter/cloud-native/container-toolkit |
| **Git** | 2.x+ | https://git-scm.com/downloads |
| **Python** (optional, local dev only) | 3.11+ | https://www.python.org/downloads |

### 1.3 Network Requirements

- Internet access is required **only during initial setup** (Docker image pulls + model download).
- After setup, the system operates **fully air-gapped / offline**.
- Outbound ports needed during setup: `443` (Docker Hub, Ollama registry).

---

## 2. Host Machine Setup

### 2.1 Windows Setup

#### Step 1 — Install WSL2 (Windows Subsystem for Linux)

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
# Reboot when prompted, then set up Ubuntu 22.04 as your distro
wsl --set-default-version 2
```

#### Step 2 — Install Docker Desktop

1. Download **Docker Desktop for Windows** from https://docs.docker.com/desktop/install/windows-install
2. During installation, enable **"Use WSL 2 based engine"**
3. After install, open Docker Desktop → **Settings → Resources → WSL Integration** → enable your Ubuntu distro
4. Verify:
   ```powershell
   docker --version
   docker compose version
   ```

#### Step 3 — Enable GPU Pass-through for Docker

1. Install the **Nvidia CUDA Toolkit** for WSL2:
   ```powershell
   # Inside WSL2 terminal (Ubuntu)
   sudo apt-get update
   sudo apt-get install -y cuda-toolkit-12-3
   ```
2. Install **Nvidia Container Toolkit** inside WSL2:
   ```bash
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```
3. Verify GPU is visible inside Docker:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi
   ```
   You should see your GPU listed.

#### Step 4 — Create Shared Output Directory

```powershell
# PowerShell (as Administrator)
New-Item -ItemType Directory -Force -Path "C:\Client_Shared\Daily_Extracts"
New-Item -ItemType Directory -Force -Path "C:\Client_Shared\DB"
# Grant full access
icacls "C:\Client_Shared" /grant Everyone:F /T
```

---

### 2.2 Ubuntu / Linux Setup

```bash
# Step 1: Update system
sudo apt-get update && sudo apt-get upgrade -y

# Step 2: Install Docker Engine
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Step 3: Add user to docker group (no-sudo docker)
sudo usermod -aG docker $USER
newgrp docker

# Step 4: Install Nvidia Container Toolkit (same as WSL2 steps above)
# ... (repeat Step 3 from Windows section)

# Step 5: Create output directories
sudo mkdir -p /opt/med-invo-mapper/outputs
sudo mkdir -p /opt/med-invo-mapper/db
sudo chmod -R 777 /opt/med-invo-mapper/
```

---

## 3. Project Structure

Clone or create the following folder layout:

```
med-invo-mapper/
├── docker-compose.yml          # Main orchestration file
├── .env                        # Environment variables (secrets, config)
├── ollama/
│   └── models/                 # Persistent model storage (volume mount)
├── agent/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # Entry point: scanner loop
│   ├── capture.py              # OpenCV camera capture & motion detection
│   ├── extractor.py            # VLM prompting & JSON parsing
│   ├── database.py             # SQLAlchemy ORM models & queries
│   ├── excel_writer.py         # openpyxl daily Excel generation
│   └── config.py               # Centralized config (reads from .env)
├── dashboard/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py                  # Streamlit monthly analytics dashboard
├── outputs/                    # ← Mounted to host: daily Excel files land here
└── db/                         # ← Mounted to host: SQLite database file
```

---

## 4. Configuration Files

### 4.1 `.env` File

Create `med-invo-mapper/.env`:

```ini
# ─── Ollama / VLM ────────────────────────────────────────────
OLLAMA_BASE_URL=http://ollama:11434
VLM_MODEL=llava:13b
# alternatives: qwen2-vl:7b, llava:7b, minicpm-v

# ─── Camera ──────────────────────────────────────────────────
CAMERA_INDEX=0              # 0 = default USB cam; change if multiple cams
CAPTURE_WIDTH=3840          # 4K; set to 1920 for 1080p
CAPTURE_HEIGHT=2160
SETTLE_SECONDS=1.8          # Seconds of stillness before triggering AI
MOTION_THRESHOLD=500        # Pixel diff threshold for motion detection

# ─── Database ────────────────────────────────────────────────
DATABASE_URL=sqlite:////app/db/med_invo.db

# ─── Output ──────────────────────────────────────────────────
OUTPUT_DIR=/app/outputs

# ─── Agent Behaviour ─────────────────────────────────────────
RETRY_ON_MISSING_FIELDS=true
MAX_RETRIES=2
LOG_LEVEL=INFO
```

### 4.2 `docker-compose.yml`

```yaml
version: "3.9"

services:

  # ─── Local VLM Server ─────────────────────────────────────
  ollama:
    image: ollama/ollama:latest
    container_name: med_ollama
    restart: unless-stopped
    ports:
      - "11434:11434"        # Exposed only on localhost
    volumes:
      - ./ollama/models:/root/.ollama   # Persist model weights on host
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    networks:
      - med_net

  # ─── AI Extraction Agent ──────────────────────────────────
  agent:
    build:
      context: ./agent
      dockerfile: Dockerfile
    container_name: med_agent
    restart: unless-stopped
    depends_on:
      - ollama
    env_file: .env
    environment:
      - DISPLAY=${DISPLAY:-:0}   # For OpenCV window preview (optional)
    volumes:
      - ./outputs:/app/outputs   # Daily Excel files → host
      - ./db:/app/db             # SQLite database → host
      - /dev/video0:/dev/video0  # USB camera pass-through (Linux)
      # Windows: camera access handled via WSL2 usbipd (see §10)
    devices:
      - /dev/video0:/dev/video0  # Linux only
    networks:
      - med_net
    # Prevent any outbound internet after startup
    # (configure via firewall rules on host; container uses internal net only)

  # ─── Monthly Analytics Dashboard ─────────────────────────
  dashboard:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    container_name: med_dashboard
    restart: unless-stopped
    ports:
      - "127.0.0.1:8501:8501"   # Streamlit, localhost only
    env_file: .env
    volumes:
      - ./db:/app/db:ro          # Read-only access to DB
      - ./outputs:/app/outputs:ro
    networks:
      - med_net

networks:
  med_net:
    driver: bridge
    internal: false   # Set to 'true' after initial model download for air-gap
```

### 4.3 `agent/Dockerfile`

```dockerfile
FROM python:3.11-slim

# System dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    v4l-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

### 4.4 `agent/requirements.txt`

```
opencv-python-headless==4.9.0.80
httpx==0.27.0
sqlalchemy==2.0.29
pandas==2.2.1
openpyxl==3.1.2
pydantic==2.7.0
python-dotenv==1.0.1
tenacity==8.2.3
Pillow==10.3.0
numpy==1.26.4
```

### 4.5 `dashboard/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.headless=true"]
```

### 4.6 `dashboard/requirements.txt`

```
streamlit==1.33.0
sqlalchemy==2.0.29
pandas==2.2.1
openpyxl==3.1.2
plotly==5.21.0
python-dotenv==1.0.1
```

---

## 5. Docker Compose Deployment

### 5.1 Initial Build & Start

```bash
# Navigate to project root
cd med-invo-mapper

# Build all service images (first time, takes 5–10 min)
docker compose build

# Start all services in detached mode
docker compose up -d

# Check all containers are healthy
docker compose ps
```

Expected output:
```
NAME              IMAGE              STATUS          PORTS
med_ollama        ollama/ollama      Up 2 minutes    0.0.0.0:11434->11434/tcp
med_agent         med_agent          Up 2 minutes
med_dashboard     med_dashboard      Up 2 minutes    127.0.0.1:8501->8501/tcp
```

### 5.2 Pull & Load the VLM Model

> [!IMPORTANT]
> This step requires internet access. Run it **before** enabling air-gap mode. The model download is ~8 GB and may take 15–30 minutes depending on connection speed.

```bash
# Pull the VLM model into the Ollama container
docker exec med_ollama ollama pull llava:13b

# Verify model is available
docker exec med_ollama ollama list
```

Expected output:
```
NAME            ID              SIZE    MODIFIED
llava:13b       ...             8.7 GB  2 minutes ago
```

**Alternative lighter model (for lower VRAM):**
```bash
docker exec med_ollama ollama pull llava:7b        # ~4 GB, 8GB VRAM
docker exec med_ollama ollama pull qwen2-vl:7b     # Strong OCR, ~4.5 GB
```

Then update `.env`:
```ini
VLM_MODEL=qwen2-vl:7b
```
And restart: `docker compose restart agent`

### 5.3 Enable Air-Gap Mode (Post Model Download)

After all models are pulled, restrict container network to local-only:

```yaml
# In docker-compose.yml, change:
networks:
  med_net:
    driver: bridge
    internal: true   # ← Block outbound internet
```

Re-apply:
```bash
docker compose down
docker compose up -d
```

---

## 6. Model Download & Verification

### 6.1 Verify VLM Inference Works

Test the model with a sample image before going live:

```bash
# Copy a test invoice image into the container
docker cp /path/to/test_invoice.jpg med_agent:/tmp/test.jpg

# Run a manual extraction test
docker exec med_agent python -c "
from extractor import extract_from_image
result = extract_from_image('/tmp/test.jpg')
print(result)
"
```

Expected JSON output:
```json
{
  "vendor_name": "Cipla Ltd.",
  "invoice_number": "INV-20240315-0042",
  "medicine_name": "Azithromycin 500mg",
  "medicine_code": "AZM500",
  "batch_number": "B2024031",
  "manufacturing_date": "2024-01",
  "expiry_date": "2026-01"
}
```

---

## 7. First-Run Validation

Run through this checklist on first deployment:

| Check | Command | Expected |
|---|---|---|
| All containers running | `docker compose ps` | All show `Up` |
| GPU visible in ollama | `docker exec med_ollama nvidia-smi` | GPU listed |
| Model loaded | `docker exec med_ollama ollama list` | Model present |
| Camera accessible | `docker exec med_agent python -c "import cv2; cap=cv2.VideoCapture(0); print(cap.isOpened())"` | `True` |
| DB initialized | `ls -la ./db/` | `med_invo.db` exists |
| Output directory writable | `ls -la ./outputs/` | Writable |
| Dashboard accessible | Open browser → `http://localhost:8501` | Streamlit UI loads |
| Agent logs clean | `docker logs med_agent --tail 50` | No ERROR lines |

---

## 8. Operational Runbook

### 8.1 Daily Operations

| Task | Command |
|---|---|
| Start the full stack | `docker compose up -d` |
| Stop the full stack | `docker compose down` |
| View live agent logs | `docker logs -f med_agent` |
| View today's Excel output | Open `./outputs/Inventory_YYYY-MM-DD.xlsx` |
| Open analytics dashboard | Browser → `http://localhost:8501` |

### 8.2 Viewing Logs

```bash
# Agent extraction logs (real-time)
docker logs -f med_agent

# Ollama model server logs
docker logs -f med_ollama

# Dashboard logs
docker logs -f med_dashboard

# All services simultaneously
docker compose logs -f
```

### 8.3 Database Inspection

```bash
# Open SQLite shell
docker exec -it med_agent python -c "
import sqlite3
conn = sqlite3.connect('/app/db/med_invo.db')
cur = conn.cursor()
cur.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
print(cur.fetchall())
conn.close()
"
```

### 8.4 Manually Triggering a Re-Extraction

If a document was placed incorrectly and you need to re-process:

```bash
# Place the document again in front of camera
# OR copy an image manually and trigger extraction
docker exec med_agent python -c "
from extractor import extract_from_image
from excel_writer import append_to_excel
from database import log_transaction
result = extract_from_image('/app/outputs/manual_test.jpg')
log_transaction(result)
append_to_excel(result)
print('Done:', result)
"
```

### 8.5 Backup Procedure

```bash
# Backup DB + Excel outputs (run from host)
$date = Get-Date -Format "yyyy-MM-dd"

# Windows PowerShell
Compress-Archive -Path ".\db\", ".\outputs\" -DestinationPath ".\backup_$date.zip"

# Linux / WSL2 bash
tar -czf backup_$(date +%Y-%m-%d).tar.gz ./db/ ./outputs/
```

---

## 9. Auto-Start on Boot

### 9.1 Windows — Task Scheduler

1. Open **Task Scheduler** (`taskschd.msc`)
2. Create a **Basic Task**:
   - **Name:** `MedInvoAgent_AutoStart`
   - **Trigger:** At system startup
   - **Action:** Start a program
     - **Program:** `C:\Windows\System32\cmd.exe`
     - **Arguments:** `/c "cd /d D:\Divyang\work\med-invo-mapper && docker compose up -d"`
3. Under **Conditions**, uncheck "Start the task only if the computer is on AC power"
4. Under **Settings**, check "If the task is already running, do not start a new instance"

> [!TIP]
> Ensure Docker Desktop is set to **"Start Docker Desktop when you log in"** (Docker Desktop → Settings → General).

### 9.2 Linux — systemd Service

Create `/etc/systemd/system/med-invo-agent.service`:

```ini
[Unit]
Description=Medical Invoice Extraction Agent
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/med-invo-mapper
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300
User=root

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable med-invo-agent.service
sudo systemctl start med-invo-agent.service

# Verify
sudo systemctl status med-invo-agent.service
```

---

## 10. Troubleshooting

### Camera Not Detected (Windows/WSL2)

WSL2 doesn't natively expose USB devices. Use **usbipd-win**:

```powershell
# Install usbipd (run in PowerShell as Admin)
winget install --interactive --exact dorssel.usbipd-win

# List USB devices
usbipd list

# Attach camera (replace BUSID with your camera's bus ID, e.g. 2-3)
usbipd bind --busid 2-3
usbipd attach --wsl --busid 2-3

# Verify inside WSL2
lsusb | grep -i cam
ls /dev/video*
```

### GPU Not Visible Inside Container

```bash
# Verify Nvidia runtime is configured
docker info | grep -i runtime

# Should show: Runtimes: nvidia runc

# If not, reconfigure:
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Ollama Model Not Responding

```bash
# Check Ollama health
curl http://localhost:11434/api/tags

# Restart Ollama only
docker compose restart ollama

# If model is corrupted, re-pull
docker exec med_ollama ollama rm llava:13b
docker exec med_ollama ollama pull llava:13b
```

### Excel File Not Being Created

```bash
# Check output directory permissions
docker exec med_agent ls -la /app/outputs/

# Check agent logs for errors
docker logs med_agent --tail 100 | grep -i "error\|excel\|output"

# Verify host mount is working
ls -la ./outputs/
```

### High Memory / OOM Errors

```bash
# Check GPU VRAM usage
nvidia-smi

# If VRAM is full, switch to a smaller model
docker exec med_ollama ollama pull llava:7b
# Update .env → VLM_MODEL=llava:7b
docker compose restart agent
```

### Database Locked (SQLite concurrent access)

This can happen if the agent and dashboard both write simultaneously.

Solution: In `database.py`, ensure SQLAlchemy connection uses:
```python
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30}
)
```

---

## Appendix A: Database Schema Reference

```sql
-- Vendors lookup
CREATE TABLE vendors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_name TEXT NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Medicines lookup
CREATE TABLE medicines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_name TEXT NOT NULL,
    medicine_code TEXT NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Vendor ↔ Medicine mapping (agent memory)
CREATE TABLE vendor_mappings (
    vendor_id INTEGER REFERENCES vendors(id),
    medicine_id INTEGER REFERENCES medicines(id),
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (vendor_id, medicine_id)
);

-- Daily transaction log
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    vendor_id INTEGER REFERENCES vendors(id),
    medicine_id INTEGER REFERENCES medicines(id),
    invoice_number TEXT,
    batch_number TEXT,
    manufacturing_date TEXT,
    expiry_date TEXT,
    quantity INTEGER DEFAULT 1,
    raw_json TEXT,               -- Full VLM output stored for audit
    confidence_flag TEXT         -- 'OK', 'RETRY', 'MANUAL_REVIEW'
);
```

---

## Appendix B: Excel Output Format

Each daily file `Inventory_YYYY-MM-DD.xlsx` is created with the following columns:

| Column | Description |
|---|---|
| Timestamp | Exact datetime of capture |
| Vendor Name | Extracted from invoice |
| Invoice Number | Extracted from invoice |
| Medicine Name | Extracted from strip label |
| Medicine Code | Standardized code from DB |
| Batch Number | Lot/Batch from label |
| Mfg. Date | Manufacturing date |
| Exp. Date | Expiry date |
| Confidence | OK / RETRY / MANUAL REVIEW |
| Notes | Any agent comments |

---

## Appendix C: Quick Reference Command Cheatsheet

```bash
# ── Start / Stop ──────────────────────────────
docker compose up -d           # Start everything
docker compose down            # Stop everything
docker compose restart agent   # Restart only the agent

# ── Logs ──────────────────────────────────────
docker logs -f med_agent       # Stream agent logs
docker compose logs -f         # Stream all logs

# ── Model Management ──────────────────────────
docker exec med_ollama ollama list              # List models
docker exec med_ollama ollama pull llava:13b    # Pull model
docker exec med_ollama ollama rm llava:13b      # Remove model

# ── Maintenance ───────────────────────────────
docker compose pull            # Update images
docker compose build --no-cache  # Rebuild agent image
docker system prune -f         # Clean unused resources

# ── Dashboard ─────────────────────────────────
# Open: http://localhost:8501
```
