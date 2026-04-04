@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  Zelle Notifier — Windows EXE Builder
REM  Bundles everything into a single ZelleNotifier.exe (no Python needed)
REM
REM  Run this once from Command Prompt:
REM    build.bat
REM
REM  Output: dist\ZelleNotifier.exe
REM ─────────────────────────────────────────────────────────────────────────────

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Building ZelleNotifier.exe...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name ZelleNotifier ^
  --add-data "*.py;." ^
  app.py

echo.
if exist dist\ZelleNotifier.exe (
    echo  SUCCESS: dist\ZelleNotifier.exe is ready.
    echo  Copy it to the front desk PC and double-click to run.
) else (
    echo  BUILD FAILED. Check the output above for errors.
)
pause
