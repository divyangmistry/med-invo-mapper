@echo off
setlocal EnableDelayedExpansion

REM ═════════════════════════════════════════════════════════════════════════════
REM  Med-Invo Mapper — Build Script (Windows)
REM
REM  Packages the launcher + agent + dashboard into:
REM    dist\MedInvoMapper\MedInvoMapper.exe
REM
REM  Prerequisites: Run setup.bat first.
REM  Usage: Double-click build_app.bat
REM ═════════════════════════════════════════════════════════════════════════════

cd /d "%~dp0"

echo.
echo ╔════════════════════════════════════════╗
echo ║  Med-Invo Mapper — Build Native App    ║
echo ╚════════════════════════════════════════╝
echo.

REM ── Activate venv ─────────────────────────────────────────────────────────
if not exist "venv\" (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause & exit /b 1
)
call venv\Scripts\activate.bat
echo [OK]    Virtual environment activated

REM ── Ensure PyInstaller ────────────────────────────────────────────────────
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO]  Installing PyInstaller...
    pip install pyinstaller --quiet
)

REM ── Clean previous build ──────────────────────────────────────────────────
echo [INFO]  Cleaning previous build artifacts...
if exist "build\" rmdir /s /q build
if exist "dist\"  rmdir /s /q dist
echo [OK]    Build directories cleaned

REM ── Run PyInstaller ───────────────────────────────────────────────────────
echo [INFO]  Running PyInstaller (this may take a few minutes)...
pyinstaller MedInvoMapper.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause & exit /b 1
)

REM ── Post-build: working directory skeleton ────────────────────────────────
echo [INFO]  Setting up working directories in dist\...
if not exist "dist\MedInvoMapper\db\"               mkdir dist\MedInvoMapper\db
if not exist "dist\MedInvoMapper\inputs\processed\" mkdir dist\MedInvoMapper\inputs\processed
if not exist "dist\MedInvoMapper\outputs\"          mkdir dist\MedInvoMapper\outputs
if not exist "dist\MedInvoMapper\logs\"             mkdir dist\MedInvoMapper\logs
if not exist "dist\MedInvoMapper\.env"              copy /y .env.local dist\MedInvoMapper\.env >nul

echo [OK]    Working directories created

REM ── Done ──────────────────────────────────────────────────────────────────
echo.
echo [OK]    Build complete!
echo.
echo   Executable: dist\MedInvoMapper\MedInvoMapper.exe
echo.
echo   Distribute the entire dist\MedInvoMapper\ folder to the client.
echo   No Python installation required on the client machine.
echo.
pause
endlocal
