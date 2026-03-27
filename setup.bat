@echo off
setlocal EnableDelayedExpansion

REM ═════════════════════════════════════════════════════════════════════════════
REM  Med-Invo Mapper — Dependency Setup Script (Windows)
REM
REM  What this script does:
REM    1. Checks Python 3.10+
REM    2. Downloads and installs Ollama for Windows
REM    3. Pulls the required VLM model
REM    4. Creates a shared Python virtual environment (.\venv\)
REM    5. Installs all Python dependencies (agent + dashboard + launcher)
REM    6. Creates required working directories
REM    7. Copies .env.local -> .env  (skips if .env already exists)
REM    8. Prints next steps
REM
REM  Usage: Right-click -> "Run as Administrator" for best results
REM         Or double-click setup.bat
REM ═════════════════════════════════════════════════════════════════════════════

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║        Med-Invo Mapper — Setup ^& Dependency Installer        ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Script Directory ─────────────────────────────────────────────────────────
cd /d "%~dp0"

REM ─────────────────────────────────────────────────────────────────────────────
REM STEP 1 — Python Version Check
REM ─────────────────────────────────────────────────────────────────────────────
echo [INFO]  Checking Python version...

set PYTHON_CMD=
for %%P in (python3.12 python3.11 python3.10 python3 python) do (
    where %%P >nul 2>&1
    if !errorlevel! == 0 (
        for /f "tokens=2 delims= " %%V in ('%%P --version 2^>^&1') do (
            set PY_VER=%%V
        )
        set PYTHON_CMD=%%P
        goto :found_python
    )
)
echo [ERROR] Python 3.10+ is required but not found.
echo         Download from https://www.python.org/downloads/
pause
exit /b 1

:found_python
echo [OK]    Using Python !PY_VER! (!PYTHON_CMD!)

REM ─────────────────────────────────────────────────────────────────────────────
REM STEP 2 — Install Ollama
REM ─────────────────────────────────────────────────────────────────────────────
echo [INFO]  Checking Ollama installation...

where ollama >nul 2>&1
if %errorlevel% == 0 (
    for /f "tokens=*" %%V in ('ollama --version 2^>^&1') do set OLLAMA_VER=%%V
    echo [OK]    Ollama already installed (!OLLAMA_VER!)
) else (
    echo [WARN]  Ollama not found. Downloading installer...
    set OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe
    powershell -Command "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '!OLLAMA_INSTALLER!'"
    if not exist "!OLLAMA_INSTALLER!" (
        echo [ERROR] Failed to download Ollama installer.
        echo         Please download manually from https://ollama.com/download/windows
        pause
        exit /b 1
    )
    echo [INFO]  Running Ollama installer silently...
    "!OLLAMA_INSTALLER!" /S
    timeout /t 10 /nobreak >nul
    echo [OK]    Ollama installed.
    
    REM Refresh PATH
    set PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama
)

REM Start Ollama if not running
tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
if errorlevel 1 (
    echo [INFO]  Starting Ollama serve in background...
    start /b ollama serve
    timeout /t 5 /nobreak >nul
)

REM ─────────────────────────────────────────────────────────────────────────────
REM STEP 3 — Pull the VLM Model
REM ─────────────────────────────────────────────────────────────────────────────
set VLM_MODEL=qwen2.5vl:7b
echo [INFO]  Pulling VLM model: %VLM_MODEL% (may take several minutes on first run)...

ollama list 2>nul | find "qwen2.5vl" >nul
if %errorlevel% == 0 (
    echo [OK]    Model '%VLM_MODEL%' already available
) else (
    ollama pull %VLM_MODEL%
    if errorlevel 1 (
        echo [WARN]  Model pull failed. Run 'ollama pull %VLM_MODEL%' manually later.
    ) else (
        echo [OK]    Model '%VLM_MODEL%' pulled successfully
    )
)

REM ─────────────────────────────────────────────────────────────────────────────
REM STEP 4 — Create Shared Virtual Environment
REM ─────────────────────────────────────────────────────────────────────────────
echo [INFO]  Creating shared Python virtual environment at .\venv\ ...

if exist "venv\" (
    echo [WARN]  Virtual environment already exists — skipping (delete .\venv\ to recreate)
) else (
    %PYTHON_CMD% -m venv venv
    echo [OK]    Virtual environment created
)

call venv\Scripts\activate.bat
echo [OK]    Virtual environment activated

python -m pip install --upgrade pip --quiet

REM ─────────────────────────────────────────────────────────────────────────────
REM STEP 5 — Install All Python Dependencies
REM ─────────────────────────────────────────────────────────────────────────────
echo [INFO]  Installing agent dependencies...
pip install -r agent\requirements.txt --quiet
echo [OK]    Agent dependencies installed

echo [INFO]  Installing dashboard dependencies...
pip install -r dashboard\requirements.txt --quiet
echo [OK]    Dashboard dependencies installed

echo [INFO]  Installing build tools...
pip install pyinstaller --quiet
echo [OK]    Build tools installed

REM ─────────────────────────────────────────────────────────────────────────────
REM STEP 6 — Create Working Directories
REM ─────────────────────────────────────────────────────────────────────────────
echo [INFO]  Creating working directories...
if not exist "db\"               mkdir db
if not exist "inputs\processed\" mkdir inputs\processed
if not exist "outputs\"          mkdir outputs
if not exist "logs\"             mkdir logs
echo [OK]    Directories created: db\ inputs\ outputs\ logs\

REM ─────────────────────────────────────────────────────────────────────────────
REM STEP 7 — Copy .env.local -> .env
REM ─────────────────────────────────────────────────────────────────────────────
if exist ".env" (
    echo [WARN]  .env already exists — skipping (delete it to regenerate from .env.local)
) else (
    copy /y ".env.local" ".env" >nul
    echo [OK]    .env created from .env.local
)

REM ─────────────────────────────────────────────────────────────────────────────
REM DONE
REM ─────────────────────────────────────────────────────────────────────────────
echo.
echo [OK]    Setup complete!
echo.
echo   Next steps:
echo   1. Activate venv:    venv\Scripts\activate.bat
echo      Run the launcher: python launcher\app.py
echo.
echo   2. Or build the exe: build_app.bat
echo      Then run:         dist\MedInvoMapper\MedInvoMapper.exe
echo.
echo   Drop invoice images into .\inputs\ to start processing.
echo.
pause
endlocal
