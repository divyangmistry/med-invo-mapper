#!/usr/bin/env python3
"""
launcher/app.py — Med-Invo Mapper native GUI launcher.

Start / Stop the AI agent and Streamlit dashboard together
from a single window. Streams live logs from both services
and opens the dashboard in the default browser automatically.

Requirements: Python 3.10+ standard library only (tkinter).
"""
from __future__ import annotations

import os
import platform
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont
from tkinter import scrolledtext, ttk

# ── Path Detection (Frozen-aware) ──────────────────────────────────────────
_IS_FROZEN = getattr(sys, "frozen", False)

if _IS_FROZEN:
    # On macOS .app: dist/MedInvoMapper.app/Contents/MacOS/MedInvoMapper
    # Portable ROOT is next to the .app -> 4 levels up.
    _EXE = Path(sys.executable)
    if _EXE.parent.name == "MacOS" and _EXE.parent.parent.name == "Contents":
        # Package structure: ROOT / MedInvoMapper.app
        ROOT = _EXE.parent.parent.parent.parent.resolve()
    else:
        # Windows / Linux: ROOT / MedInvoMapper.exe
        ROOT = _EXE.parent.resolve()
    BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT)).resolve()
else:
    # Development mode: ROOT is the repo root
    ROOT = Path(__file__).parent.parent.resolve()
    BUNDLE_ROOT = ROOT

# ── Bundled Entry Points ──────────────────────────────────────────────────
# When frozen, we use the same executable for the agent and dashboard
if _IS_FROZEN:
    if "--agent" in sys.argv:
        # Point to the bundled agent source
        sys.path.insert(0, str(BUNDLE_ROOT / "agent"))
        # Import and run the agent main
        try:
            from agent.main import main
            main()
        except Exception as e:
            print(f"AGENT_ERROR: {e}")
        sys.exit(0)

    if "--dashboard" in sys.argv:
        # Add sources to path
        sys.path.insert(0, str(BUNDLE_ROOT))
        sys.path.insert(0, str(BUNDLE_ROOT / "dashboard"))
        import streamlit.web.cli as stcli
        # Re-construct sys.argv for 'streamlit run dashboard/app.py ...'
        sys.argv = [
            "streamlit", "run",
            str(BUNDLE_ROOT / "dashboard" / "app.py"),
            "--server.headless", "true",
        ] + [a for a in sys.argv if a not in ("--dashboard", sys.executable)]
        sys.exit(stcli.main())

# ── Resolve executables (Dev mode only) ───────────────────────────────────
VENV_DIR = ROOT / "venv"
IS_WINDOWS = platform.system() == "Windows"

if not _IS_FROZEN:
    if IS_WINDOWS:
        PYTHON_BIN   = VENV_DIR / "Scripts" / "python.exe"
        STREAMLIT_BIN = VENV_DIR / "Scripts" / "streamlit.exe"
    else:
        PYTHON_BIN   = VENV_DIR / "bin" / "python"
        STREAMLIT_BIN = VENV_DIR / "bin" / "streamlit"

    # Fall back to system python if venv doesn't exist yet
    if not PYTHON_BIN.exists():
        PYTHON_BIN = Path(sys.executable)
else:
    # Frozen mode uses the executable itself
    PYTHON_BIN   = Path(sys.executable)
    STREAMLIT_BIN = Path(sys.executable)

DASHBOARD_PORT = 8501

# ── Colours ────────────────────────────────────────────────────────────────
CLR_BG       = "#1a1a2e"
CLR_SURFACE  = "#16213e"
CLR_ACCENT   = "#0f3460"
CLR_PRIMARY  = "#e94560"
CLR_SUCCESS  = "#4ecca3"
CLR_WARNING  = "#ffd460"
CLR_TEXT     = "#eaeaea"
CLR_SUBTEXT  = "#888888"
CLR_AGENT    = "#4ecca3"
CLR_DASH     = "#7eb8f7"


# ═══════════════════════════════════════════════════════════════════════════
class MedInvoApp(tk.Tk):
    """Main launcher window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Med-Invo Mapper")
        self.configure(bg=CLR_BG)
        self.resizable(True, True)
        self.minsize(820, 580)

        # ── State ──────────────────────────────────────────────────────────
        self._agent_proc:  subprocess.Popen | None = None
        self._dash_proc:   subprocess.Popen | None = None
        self._log_queue:   queue.Queue[str] = queue.Queue()
        self._running      = False

        self._agent_status = tk.StringVar(value="Stopped")
        self._dash_status  = tk.StringVar(value="Stopped")

        # UI components initialized in _build_ui
        self._agent_dot: tk.Label | None = None
        self._dash_dot:  tk.Label | None = None
        self._start_btn: tk.Button | None = None
        self._stop_btn:  tk.Button | None = None
        self._open_btn:  tk.Button | None = None
        self._log_box:   scrolledtext.ScrolledText | None = None

        self._build_ui()
        self._schedule_log_drain()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Centre window
        self.update_idletasks()
        w, h = 900, 640
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Header ────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=CLR_ACCENT, pady=14)
        header.pack(fill="x")

        title_font = tkfont.Font(family="Helvetica", size=18, weight="bold")
        sub_font   = tkfont.Font(family="Helvetica", size=10)

        tk.Label(header, text="💊  Med-Invo Mapper",
                 bg=CLR_ACCENT, fg=CLR_TEXT,
                 font=title_font).pack(side="left", padx=20)
        tk.Label(header, text="Medical Invoice & Label Extraction Agent",
                 bg=CLR_ACCENT, fg=CLR_SUBTEXT,
                 font=sub_font).pack(side="left", padx=4)

        # ── Status Bar ────────────────────────────────────────────────────
        status_frame = tk.Frame(self, bg=CLR_SURFACE, pady=10)
        status_frame.pack(fill="x", padx=0)

        self._agent_dot = tk.Label(status_frame, text="●", fg=CLR_PRIMARY,
                                   bg=CLR_SURFACE, font=("Helvetica", 14))
        self._agent_dot.pack(side="left", padx=(20, 4))
        tk.Label(status_frame, textvariable=self._agent_status,
                 bg=CLR_SURFACE, fg=CLR_TEXT,
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 20))

        self._dash_dot = tk.Label(status_frame, text="●", fg=CLR_PRIMARY,
                                  bg=CLR_SURFACE, font=("Helvetica", 14))
        self._dash_dot.pack(side="left", padx=(10, 4))
        tk.Label(status_frame, textvariable=self._dash_status,
                 bg=CLR_SURFACE, fg=CLR_TEXT,
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 20))

        # ── Button Row ────────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=CLR_BG, pady=14)
        btn_frame.pack(fill="x", padx=20)

        btn_style = dict(
            font=("Helvetica", 12, "bold"),
            relief="flat", cursor="hand2",
            padx=24, pady=8, bd=0,
        )

        self._start_btn = tk.Button(
            btn_frame, text="▶  Start",
            bg=CLR_SUCCESS, fg=CLR_BG,
            command=self._start_services,
            **btn_style,
        )
        self._start_btn.pack(side="left", padx=(0, 12))

        self._stop_btn = tk.Button(
            btn_frame, text="■  Stop",
            bg=CLR_PRIMARY, fg=CLR_TEXT,
            command=self._stop_services,
            state="disabled",
            **btn_style,
        )
        self._stop_btn.pack(side="left", padx=(0, 12))

        self._open_btn = tk.Button(
            btn_frame, text="🌐  Open Dashboard",
            bg=CLR_ACCENT, fg=CLR_TEXT,
            command=self._open_browser,
            **btn_style,
        )
        self._open_btn.pack(side="left")

        # ── Log Pane ─────────────────────────────────────────────────────
        log_frame = tk.Frame(self, bg=CLR_BG)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        tk.Label(log_frame, text="  Live Logs",
                 bg=CLR_BG, fg=CLR_SUBTEXT,
                 font=("Helvetica", 9)).pack(anchor="w")

        self._log_box = scrolledtext.ScrolledText(
            log_frame,
            bg="#0d0d1a", fg=CLR_TEXT,
            font=("Courier", 10),
            relief="flat",
            state="disabled",
            wrap="word",
        )
        self._log_box.pack(fill="both", expand=True)

        # Colour tags for log output
        self._log_box.tag_config("agent", foreground=CLR_AGENT)
        self._log_box.tag_config("dash",  foreground=CLR_DASH)
        self._log_box.tag_config("warn",  foreground=CLR_WARNING)
        self._log_box.tag_config("err",   foreground=CLR_PRIMARY)
        self._log_box.tag_config("info",  foreground=CLR_TEXT)

        # ── Footer ────────────────────────────────────────────────────────
        footer = tk.Frame(self, bg=CLR_SURFACE, pady=6)
        footer.pack(fill="x")
        tk.Label(footer,
                 text=f"  Root: {ROOT}   |   Dashboard: http://localhost:{DASHBOARD_PORT}",
                 bg=CLR_SURFACE, fg=CLR_SUBTEXT,
                 font=("Helvetica", 9)).pack(side="left", padx=10)

    # ── Service Management ─────────────────────────────────────────────────

    def _start_services(self) -> None:
        if self._running:
            return
        self._running = True
        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")

        env = {**os.environ, "PYTHONPATH": str(ROOT / "agent")}
        env["PYTHONUNBUFFERED"] = "1"

        # Load .env into the subprocess environment
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip() # Override existing env vars
            
            # Override paths to absolute values
            for k in ("OUTPUT_DIR", "INPUT_DIR", "LOG_DIR"):
                if k in env:
                    path = Path(env[k])
                    if not path.is_absolute():
                        env[k] = str(ROOT / path)
            if "DATABASE_URL" in env:
                db_url = env["DATABASE_URL"]
                prefix = "sqlite:///./"
                if db_url.startswith(prefix):
                    rel = db_url[len(prefix):]
                    env["DATABASE_URL"] = f"sqlite:///{ROOT / rel}"
        
        self._log(f"[LAUNCHER] Project Root: {ROOT}", "info")
        self._log(f"[LAUNCHER] Database URL: {env.get('DATABASE_URL', 'Default')}", "info")

        # Ensure dirs exist
        for d in ["db", "inputs", "inputs/processed", "outputs", "logs"]:
            (ROOT / d).mkdir(parents=True, exist_ok=True)

        # ── Start Agent ────────────────────────────────────────────────────
        self._log("[LAUNCHER] Starting agent...", "info")
        agent_cmd = [str(PYTHON_BIN)]
        if _IS_FROZEN:
            agent_cmd.append("--agent")
        else:
            agent_cmd.append(str(ROOT / "agent" / "main.py"))

        try:
            self._agent_proc = subprocess.Popen(
                agent_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT),
                env=env,
                text=True,
                bufsize=1,
            )
            threading.Thread(
                target=self._pipe_reader,
                args=(self._agent_proc, "agent"),
                daemon=True,
            ).start()
            self._set_status("agent", "running")
        except Exception as exc:
            self._log(f"[LAUNCHER] Failed to start agent: {exc}", "err")
            self._set_status("agent", "error")

        # ── Start Dashboard ────────────────────────────────────────────────
        self._log("[LAUNCHER] Starting dashboard...", "info")
        if _IS_FROZEN:
            dash_cmd = [str(PYTHON_BIN), "--dashboard"]
        else:
            dash_cmd = self._resolve_streamlit() + [str(ROOT / "dashboard" / "app.py")]

        try:
            self._dash_proc = subprocess.Popen(
                dash_cmd + [
                    "--server.port", str(DASHBOARD_PORT),
                    "--server.headless", "true",
                    "--server.address", "localhost",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT),
                env=env,
                text=True,
                bufsize=1,
            )
            threading.Thread(
                target=self._pipe_reader,
                args=(self._dash_proc, "dash"),
                daemon=True,
            ).start()
            self._set_status("dash", "running")
        except Exception as exc:
            self._log(f"[LAUNCHER] Failed to start dashboard: {exc}", "err")
            self._set_status("dash", "error")

        # Open browser after a short delay
        self.after(4000, self._open_browser)

    def _stop_services(self) -> None:
        if not self._running:
            return
        self._log("[LAUNCHER] Stopping services...", "warn")

        for proc, name in [
            (self._agent_proc, "agent"),
            (self._dash_proc, "dashboard"),
        ]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                self._log(f"[LAUNCHER] {name} stopped.", "warn")

        self._agent_proc = None
        self._dash_proc  = None
        self._running    = False

        self._set_status("agent", "stopped")
        self._set_status("dash",  "stopped")
        self._start_btn.config(state="normal")
        self._stop_btn.config(state="disabled")

    def _open_browser(self) -> None:
        url = f"http://localhost:{DASHBOARD_PORT}"
        self._log(f"[LAUNCHER] Opening {url} in browser...", "info")
        webbrowser.open(url)

    def _resolve_streamlit(self) -> list[str]:
        """Return the command list to invoke streamlit."""
        if STREAMLIT_BIN and STREAMLIT_BIN.exists():
            return [str(STREAMLIT_BIN), "run"]
        # Fall back: python -m streamlit run
        return [str(PYTHON_BIN), "-m", "streamlit", "run"]

    # ── Log Handling ───────────────────────────────────────────────────────

    def _pipe_reader(self, proc: subprocess.Popen, tag: str) -> None:
        """Read subprocess stdout in a background thread and push to queue."""
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    t = "err" if any(w in line.lower() for w in ("error", "critical", "traceback")) \
                        else "warn" if "warn" in line.lower() \
                        else tag
                    self._log_queue.put((line, t))
        except Exception:
            pass
        finally:
            name = "Agent" if tag == "agent" else "Dashboard"
            self._log_queue.put((f"[LAUNCHER] {name} process exited.", "warn"))
            if self._running:
                self.after(0, lambda: self._set_status(tag, "stopped"))

    def _schedule_log_drain(self) -> None:
        """Drain the log queue every 100 ms from the main thread."""
        try:
            for _ in range(50):      # batch up to 50 lines per tick
                item = self._log_queue.get_nowait()
                if isinstance(item, tuple):
                    text, tag = item
                else:
                    text, tag = item, "info"
                self._log(text, tag)
        except queue.Empty:
            pass
        self.after(100, self._schedule_log_drain)

    def _log(self, message: str, tag: str = "info") -> None:
        ts = time.strftime("%H:%M:%S")
        self._log_box.config(state="normal")
        self._log_box.insert("end", f"[{ts}] {message}\n", tag)
        self._log_box.see("end")
        self._log_box.config(state="disabled")

    # ── Status Indicators ─────────────────────────────────────────────────

    def _set_status(self, service: str, state: str) -> None:
        colour = {
            "running": CLR_SUCCESS,
            "stopped": CLR_PRIMARY,
            "error":   CLR_WARNING,
        }.get(state, CLR_SUBTEXT)

        label = {
            "running": f"{'Agent' if service == 'agent' else 'Dashboard'}: Running",
            "stopped": f"{'Agent' if service == 'agent' else 'Dashboard'}: Stopped",
            "error":   f"{'Agent' if service == 'agent' else 'Dashboard'}: Error",
        }.get(state, state)

        if service == "agent" and self._agent_dot:
            self._agent_dot.config(fg=colour)
            self._agent_status.set(label)
        elif service == "dash" and self._dash_dot:
            self._dash_dot.config(fg=colour)
            self._dash_status.set(label)

    # ── Window Close ──────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self._running:
            self._stop_services()
        self.destroy()


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = MedInvoApp()
    app.mainloop()
