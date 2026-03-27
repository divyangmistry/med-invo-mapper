#!/usr/bin/env bash
# ═════════════════════════════════════════════════════════════════════════════
#  Med-Invo Mapper — Build Script (macOS / Linux)
#
#  Packages the launcher + agent + dashboard into a self-contained bundle.
#
#  On macOS produces:  dist/MedInvoMapper.app
#  On Linux produces:  dist/MedInvoMapper/  (folder with executable inside)
#
#  Prerequisites:
#    Run setup.sh first to create the venv and install all dependencies.
#
#  Usage:
#    chmod +x build_app.sh
#    ./build_app.sh
# ═════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║  Med-Invo Mapper — Build Native App  ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""

# ── Resolve venv binaries ──────────────────────────────────────────────────
VENV_PYTHON="./venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    error "Virtual environment python not found at $VENV_PYTHON. Please run setup.sh first."
fi
success "Using virtual environment Python"

# ── Ensure PyInstaller is available ──────────────────────────────────────────
if ! "$VENV_PYTHON" -m PyInstaller --version &>/dev/null; then
    info "Installing PyInstaller..."
    "$VENV_PYTHON" -m pip install pyinstaller --quiet
fi

# ── Clean previous build ──────────────────────────────────────────────────────
info "Cleaning previous build artifacts..."
rm -rf build/ dist/
success "Build directories cleaned"

# ── Run PyInstaller ───────────────────────────────────────────────────────────
info "Running PyInstaller (this may take a few minutes)..."
"$VENV_PYTHON" -m PyInstaller MedInvoMapper.spec --noconfirm

# ── Post-build: Create Portable Data Structure ──────────────────────────────
info "Creating portable data structure..."

# For macOS, data should be next to MedInvoMapper.app in dist/
# For Windows/Linux, data should be next to the executable in dist/MedInvoMapper/
if [ "$(uname -s)" = "Darwin" ]; then
    PORTABLE_ROOT="dist"
else
    PORTABLE_ROOT="dist/MedInvoMapper"
fi

mkdir -p "$PORTABLE_ROOT/db" \
         "$PORTABLE_ROOT/inputs/processed" \
         "$PORTABLE_ROOT/outputs" \
         "$PORTABLE_ROOT/logs"

# Copy .env.local to .env if it doesn't exist
if [ ! -f "$PORTABLE_ROOT/.env" ]; then
    cp .env.local "$PORTABLE_ROOT/.env"
    success ".env created from template in portable root"
fi

success "Portable working directories created in $PORTABLE_ROOT"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✔  Build complete!${RESET}"
echo ""
if [ "$(uname -s)" = "Darwin" ]; then
    echo -e "  ${BOLD}macOS app:${RESET}  ${CYAN}open dist/MedInvoMapper.app${RESET}"
fi
echo -e "  ${BOLD}Folder:${RESET}     ${CYAN}dist/MedInvoMapper/${RESET}"
echo ""
echo -e "  Distribute the entire ${CYAN}dist/${RESET} folder to the client."
echo -e "  No Python installation required on the client machine."
echo ""
