# -*- mode: python ; coding: utf-8 -*-
# ═════════════════════════════════════════════════════════════════════════════
#  PyInstaller Spec — Med-Invo Mapper
#
#  Produces a directory bundle (.app on macOS, folder on Windows) containing:
#    • The tkinter launcher (entry point)
#    • The full agent/ package
#    • The full dashboard/ package
#    • All Python dependencies from the shared venv
#    • The .env.local template
#
#  Build with:   bash build_app.sh      (macOS/Linux)
#                build_app.bat          (Windows)
# ═════════════════════════════════════════════════════════════════════════════

import sys
from pathlib import Path

ROOT = Path(SPECPATH)   # project root (where this .spec file lives)

# ── Collect package data that Streamlit needs at runtime ────────────────────
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata, collect_dynamic_libs

streamlit_datas   = collect_data_files("streamlit",   include_py_files=True)
streamlit_metadata = copy_metadata("streamlit")
plotly_datas      = collect_data_files("plotly",      include_py_files=False)
altair_datas      = collect_data_files("altair",      include_py_files=False)
sqlalchemy_datas  = collect_data_files("sqlalchemy",  include_py_files=False)

hidden_imports = (
    collect_submodules("streamlit")
    + collect_submodules("sqlalchemy")
    + collect_submodules("sqlalchemy.dialects.sqlite")
    + collect_submodules("watchdog")
    + collect_submodules("plotly")
    + collect_submodules("pandas")
    + [
        "tkinter", "tkinter.scrolledtext", "tkinter.font", "tkinter.ttk",
        "PIL._tkinter_finder",
        "httpx", "tenacity", "openpyxl",
        "cv2",    # OpenCV — needed for live camera mode
        "pytesseract",
    ]
)

# ── Source data to bundle ────────────────────────────────────────────────────
datas = [
    # Agent source
    (str(ROOT / "agent"),     "agent"),
    # Dashboard source
    (str(ROOT / "dashboard"), "dashboard"),
    # Env template
    (str(ROOT / ".env.local"), "."),
]
datas += streamlit_datas
datas += streamlit_metadata
datas += plotly_datas
datas += altair_datas
datas += sqlalchemy_datas

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "launcher" / "app.py")],
    pathex=[str(ROOT / "agent"), str(ROOT / "dashboard")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["_bootsubprocess", "IPython", "jupyter", "matplotlib"],
    win_no_prefer_redirects=False,
    noarchive=False,
)

# ── Binary Filter (macOS logic to fix OpenCV/SSL conflict) ──────────────────
if sys.platform == "darwin":
    print(" [SPEC] Applying macOS-specific OpenSSL conflict fixes...")
    
    # 1. Define the Homebrew OpenSSL path (usually where Python gets its libs)
    openssl_path = Path("/opt/homebrew/opt/openssl@3/lib")
    if not openssl_path.exists():
        openssl_path = Path("/usr/local/opt/openssl@3/lib")
    
    if openssl_path.exists():
        print(f" [SPEC] Found Homebrew OpenSSL at: {openssl_path}")
        
        # 2. Extract libraries we want to prioritize
        good_libs = [
            ("Frameworks/libssl.3.dylib",    str(openssl_path / "libssl.3.dylib"),    "BINARY"),
            ("Frameworks/libcrypto.3.dylib", str(openssl_path / "libcrypto.3.dylib"), "BINARY"),
        ]

        
        # 3. Filter current binaries: remove ANY libcrypto/libssl that are NOT from our good path
        # This prevents cv2's older bundled versions from shadowing the good ones.
        new_binaries = []
        for name, path, type_ in a.binaries:
            # Check if this binary is one of the OpenSSL libs
            is_ssl = "libssl.3" in name or "libssl.3" in path
            is_crypto = "libcrypto.3" in name or "libcrypto.3" in path
            
            if is_ssl or is_crypto:
                # If it's already from the homebrew path, we'll keep it (or let our good_libs replace it)
                if str(openssl_path) in path:
                    continue 
                # If it's from cv2 or elsewhere, EXCLUDE it
                print(f" [SPEC] Excluding potentially incompatible OpenSSL binary: {name} from {path}")
                continue
            
            new_binaries.append((name, path, type_))
        
        # 4. Update a.binaries with filtered list + our guaranteed good libs
        a.binaries = new_binaries + good_libs
        print(" [SPEC] OpenSSL conflict fix applied (prioritizing 3.6.1+ from Homebrew).")
    else:
        print(" [WARNING] Homebrew OpenSSL 3 lib folder not found. Falling back to default analysis.")


pyz = PYZ(a.pure, a.zipped_data)

# ── Executable ───────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MedInvoMapper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,         # No terminal window on Windows
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,             # Add path to .icns / .ico here if you have one
)

# ── Directory Collection ──────────────────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MedInvoMapper",
)

# ── macOS .app Bundle ─────────────────────────────────────────────────────────
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MedInvoMapper.app",
        icon=None,              # Replace with "assets/icon.icns" if available
        bundle_identifier="com.medinvomapper.launcher",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleDisplayName": "Med-Invo Mapper",
            "CFBundleVersion": "1.0.0",
            "CFBundleShortVersionString": "1.0.0",
            "NSCameraUsageDescription": "Used for live invoice capture in camera mode.",
        },
    )
