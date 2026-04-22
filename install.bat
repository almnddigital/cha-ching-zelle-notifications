@echo off
REM Cha-Ching Payment Notifications — double-click installer/updater
REM
REM Just double-click install.bat. It runs install-chaching.ps1 with the
REM right PowerShell flags and leaves the window open so you can read the
REM output (or any errors).

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0install-chaching.ps1"

echo.
echo Press any key to close this window.
pause >nul
