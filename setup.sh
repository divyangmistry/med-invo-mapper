#!/usr/bin/env bash
# ═════════════════════════════════════════════════════════════════════════════
#  Med-Invo Mapper — Dependency Setup Script (macOS / Linux)
#
#  What this script does:
#    1. Checks Python 3.10+
#    2. Installs Ollama (via Homebrew on macOS, or curl installer on Linux)
#    3. Pulls the required VLM model
#    4. Creates a shared Python virtual environment (./venv/)
#    5. Installs all Python dependencies (agent + dashboard + launcher)
#    6. Creates required working directories
#    7. Copies .env.local → .env  (skips if .env already exists)
#    8. Prints next steps
#
#  Usage:
#    chmod +x setup.sh
#    ./setup.sh
# ═════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ── Script Directory (project root) ──────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║        Med-Invo Mapper — Setup & Dependency Installer        ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Python Version Check
# ─────────────────────────────────────────────────────────────────────────────
info "Checking Python version..."

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')")
        if [ "$VER" -ge 310 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    error "Python 3.10 or higher is required but not found.
       Install it from https://www.python.org/downloads/ and re-run this script."
fi

PY_VERSION=$("$PYTHON" --version)
success "Using $PY_VERSION"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Install Ollama
# ─────────────────────────────────────────────────────────────────────────────
info "Checking Ollama installation..."

if command -v ollama &>/dev/null; then
    OLLAMA_VER=$(ollama --version 2>/dev/null || echo "unknown")
    success "Ollama already installed ($OLLAMA_VER)"
else
    warn "Ollama not found. Installing..."

    OS="$(uname -s)"
    if [ "$OS" = "Darwin" ]; then
        # macOS — try Homebrew first, then DMG download
        if command -v brew &>/dev/null; then
            info "Installing Ollama via Homebrew..."
            brew install ollama
        else
            info "Downloading Ollama for macOS..."
            OLLAMA_DMG="/tmp/Ollama-macOS.zip"
            curl -fsSL "https://ollama.com/download/Ollama-darwin.zip" -o "$OLLAMA_DMG"
            info "Extracting Ollama..."
            unzip -o "$OLLAMA_DMG" -d /tmp/ollama_extract
            # Move Ollama.app to /Applications
            if [ -d "/tmp/ollama_extract/Ollama.app" ]; then
                cp -R "/tmp/ollama_extract/Ollama.app" /Applications/
                success "Ollama.app installed to /Applications/"
                info "Starting Ollama service..."
                open -a Ollama
                sleep 5
            else
                error "Could not find Ollama.app in the downloaded archive."
            fi
            rm -rf "$OLLAMA_DMG" /tmp/ollama_extract
        fi
    elif [ "$OS" = "Linux" ]; then
        info "Installing Ollama via official installer..."
        curl -fsSL https://ollama.com/install.sh | sh
    else
        error "Unsupported OS: $OS. Please install Ollama manually from https://ollama.com/download"
    fi

    # Start Ollama service if not running
    if ! pgrep -x "ollama" &>/dev/null; then
        info "Starting Ollama serve in the background..."
        ollama serve &>/dev/null &
        sleep 3
    fi

    success "Ollama installed successfully"
fi

# Ensure Ollama daemon is running
if ! ollama list &>/dev/null; then
    info "Starting Ollama serve..."
    ollama serve &>/dev/null &
    sleep 5
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Pull the VLM Model
# ─────────────────────────────────────────────────────────────────────────────
VLM_MODEL="${VLM_MODEL:-qwen2.5vl:7b}"
info "Pulling VLM model: $VLM_MODEL (this may take several minutes on first run)..."

if ollama list | grep -q "${VLM_MODEL%:*}"; then
    success "Model '$VLM_MODEL' is already available"
else
    ollama pull "$VLM_MODEL" || warn "Model pull failed — you can run 'ollama pull $VLM_MODEL' manually later"
    success "Model '$VLM_MODEL' pulled successfully"
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Create Shared Virtual Environment
# ─────────────────────────────────────────────────────────────────────────────
info "Creating shared Python virtual environment at ./venv/ ..."

if [ -d "venv" ]; then
    warn "Virtual environment already exists — skipping creation (delete ./venv/ and re-run to recreate)"
else
    "$PYTHON" -m venv venv
    success "Virtual environment created"
fi

# Activate
source venv/bin/activate
success "Virtual environment activated"

# Upgrade pip silently
pip install --upgrade pip --quiet

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Install All Python Dependencies
# ─────────────────────────────────────────────────────────────────────────────
info "Installing agent dependencies..."
pip install -r agent/requirements.txt --quiet
success "Agent dependencies installed"

info "Installing dashboard dependencies..."
pip install -r dashboard/requirements.txt --quiet
success "Dashboard dependencies installed"

info "Installing launcher dependencies..."
# Launcher uses only stdlib (tkinter) — just ensure pyinstaller is available for building
pip install pyinstaller --quiet
success "Launcher / build dependencies installed"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Create Working Directories
# ─────────────────────────────────────────────────────────────────────────────
info "Creating working directories..."
mkdir -p db inputs/processed outputs logs
success "Directories created: db/ inputs/ outputs/ logs/"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Copy .env.local → .env
# ─────────────────────────────────────────────────────────────────────────────
if [ -f ".env" ]; then
    warn ".env already exists — skipping copy (delete it to regenerate from .env.local)"
else
    cp .env.local .env
    success ".env created from .env.local"
fi

# ─────────────────────────────────────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✔  Setup complete!${RESET}"
echo ""
echo -e "  ${BOLD}Next steps:${RESET}"
echo -e "  1. Run the launcher:    ${CYAN}source venv/bin/activate && python launcher/app.py${RESET}"
echo -e "  2. Or build the .app:   ${CYAN}bash build_app.sh${RESET}"
echo -e "     Then open:           ${CYAN}open dist/MedInvoMapper.app${RESET}"
echo ""
echo -e "  Drop invoice images into ${CYAN}./inputs/${RESET} to start processing."
echo ""
