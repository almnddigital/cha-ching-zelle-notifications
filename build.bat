@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  Cha-Ching Payment Notifications — Windows EXE Builder
REM  Bundles everything into a single ChaChing.exe (no Python needed)
REM
REM  Run this once from Command Prompt:
REM    build.bat
REM
REM  Output: dist\ChaChing.exe
REM ─────────────────────────────────────────────────────────────────────────────

setlocal
set "BUILD_PYTHON=.venv-build\Scripts\python.exe"

if not exist "%BUILD_PYTHON%" (
    echo Creating isolated build environment...
    python -m venv .venv-build
    if errorlevel 1 goto :failed
)

echo Installing pinned dependencies...
"%BUILD_PYTHON%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

echo Running tests...
"%BUILD_PYTHON%" -m unittest -v
if errorlevel 1 goto :failed

echo.
echo Building ChaChing.exe...
"%BUILD_PYTHON%" -m PyInstaller ^
  --clean ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name ChaChing ^
  --hidden-import win32crypt ^
  --hidden-import win32event ^
  --hidden-import win32api ^
  --collect-all customtkinter ^
  --add-data "chachingsound.wav;." ^
  app.py
if errorlevel 1 goto :failed

echo.
if exist dist\ChaChing.exe (
    powershell.exe -NoProfile -Command "$h=(Get-FileHash 'dist\ChaChing.exe' -Algorithm SHA256).Hash.ToLowerInvariant(); Set-Content -NoNewline 'dist\ChaChing.exe.sha256' ($h + '  ChaChing.exe')"
    if errorlevel 1 goto :failed
    echo  SUCCESS: dist\ChaChing.exe is ready.
    echo  SUCCESS: dist\ChaChing.exe.sha256 is ready.
    echo  Copy it to the front desk PC and double-click to run.
) else (
    goto :failed
)
if not defined CI pause
exit /b 0

:failed
echo.
echo  BUILD FAILED. Check the output above for errors.
if not defined CI pause
exit /b 1
