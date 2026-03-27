"""
config.py — Centralised configuration.
All settings are sourced from environment variables (loaded from .env by Docker
or by python-dotenv when running tests locally).
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ── Frozen (PyInstaller) detection ──────────────────────────────────────────
_IS_FROZEN = getattr(sys, "frozen", False)

if _IS_FROZEN:
    # When bundled, sys.executable is the binary.
    # On macOS .app: dist/MedInvoMapper.app/Contents/MacOS/MedInvoMapper
    # Data should be next to the .app -> 4 levels up.
    _EXE = Path(sys.executable)
    if _EXE.parent.name == "MacOS" and _EXE.parent.parent.name == "Contents":
        _PROJECT_ROOT = _EXE.parent.parent.parent.parent.resolve()
    else:
        # Windows/Linux: executable is in the same folder as data
        _PROJECT_ROOT = _EXE.parent.resolve()
    # Path to bundled resources (standard PyInstaller)
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", _PROJECT_ROOT)).resolve()
else:
    # Development: repo root (assuming config.py is in agent/)
    _PROJECT_ROOT = Path(__file__).parent.parent.resolve()
    _BUNDLE_ROOT = _PROJECT_ROOT


# Allow running agent scripts directly (outside Docker) for tests
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env.dev", override=False)

# ── Docker vs. native detection ───────────────────────────────────────────
# When /.dockerenv exists we are inside a container; otherwise native install.
_IN_DOCKER = Path("/.dockerenv").exists()


class Config:
    # ── VLM / Ollama ─────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    VLM_MODEL: str = os.getenv("VLM_MODEL", "qwen2-vl:7b")
    VLM_TIMEOUT: int = int(os.getenv("VLM_TIMEOUT", "120"))
    VLM_TEMPERATURE: float = float(os.getenv("VLM_TEMPERATURE", "0.0"))

    # ── Camera / Capture ─────────────────────────────────────────────────────
    CAMERA_MODE: str = os.getenv("CAMERA_MODE", "folder")   # 'folder' | 'live'
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
    CAPTURE_WIDTH: int = int(os.getenv("CAPTURE_WIDTH", "1920"))
    CAPTURE_HEIGHT: int = int(os.getenv("CAPTURE_HEIGHT", "1080"))
    SETTLE_SECONDS: float = float(os.getenv("SETTLE_SECONDS", "1.8"))
    MOTION_THRESHOLD: int = int(os.getenv("MOTION_THRESHOLD", "500"))

    # ── Database ─────────────────────────────────────────────────────────────
    _raw_db_url = os.getenv(
        "DATABASE_URL",
        "sqlite:////app/db/med_invo.db" if _IN_DOCKER
        else f"sqlite:///{_PROJECT_ROOT / 'db' / 'med_invo.db'}"
    )
    # Smart resolution for relative paths (sqlite:///./...)
    if _raw_db_url.startswith("sqlite:///./") and not _IN_DOCKER:
        _rel_path = _raw_db_url[len("sqlite:///./"):]
        DATABASE_URL = f"sqlite:///{_PROJECT_ROOT / _rel_path}"
    else:
        DATABASE_URL = _raw_db_url


    # ── Directories ──────────────────────────────────────────────────────────
    _default_output = "/app/outputs"  if _IN_DOCKER else str(_PROJECT_ROOT / "outputs")
    _default_input  = "/app/inputs"   if _IN_DOCKER else str(_PROJECT_ROOT / "inputs")
    _default_log    = "/app/logs"     if _IN_DOCKER else str(_PROJECT_ROOT / "logs")

    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", _default_output))
    INPUT_DIR:  Path = Path(os.getenv("INPUT_DIR",  _default_input))
    LOG_DIR:    Path = Path(os.getenv("LOG_DIR",    _default_log))

    # ── Agent Behaviour ──────────────────────────────────────────────────────
    RETRY_ON_MISSING_FIELDS: bool = os.getenv("RETRY_ON_MISSING_FIELDS", "true").lower() == "true"
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "2"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ── Derived / Computed ───────────────────────────────────────────────────
    @classmethod
    def ensure_dirs(cls) -> None:
        """Create all required runtime directories if they don't exist."""
        for d in [cls.OUTPUT_DIR, cls.INPUT_DIR, cls.LOG_DIR,
                  cls.INPUT_DIR / "processed"]:
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def summary(cls) -> str:
        return (
            f"Model={cls.VLM_MODEL} | Mode={cls.CAMERA_MODE} | "
            f"DB={cls.DATABASE_URL} | OutDir={cls.OUTPUT_DIR}"
        )
