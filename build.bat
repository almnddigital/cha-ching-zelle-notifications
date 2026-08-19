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

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Building ChaChing.exe...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name ChaChing ^
  --hidden-import win32crypt ^
  --add-data "*.py;." ^
  --add-data "chachingsound.wav;." ^
  app.py

echo.
if exist dist\ChaChing.exe (
    echo  SUCCESS: dist\ChaChing.exe is ready.
    echo  Copy it to the front desk PC and double-click to run.
) else (
    echo  BUILD FAILED. Check the output above for errors.
)
pause
