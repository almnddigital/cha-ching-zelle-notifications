# Cha-Ching Payment Notifications — installer + updater
#
# First install: run this script on the front-desk PC. It will download the
# latest release, install to %USERPROFILE%\ChaChing, create Desktop and Startup
# shortcuts, and launch the app.
#
# Update: just re-run this script any time. It stops the running tray app,
# overwrites the EXE with the latest release, and relaunches. Shortcuts are
# reused if they already exist.
#
# Usage:
#   Right-click install-chaching.ps1 -> Run with PowerShell
#   (or from a PowerShell window: .\install-chaching.ps1)

$ErrorActionPreference = "Stop"

$Repo = "almnddigital/cha-ching-zelle-notifications"
$InstallDir = Join-Path $env:USERPROFILE "ChaChing"
$ExePath = Join-Path $InstallDir "ChaChing.exe"

Write-Host "Fetching latest release from github.com/$Repo ..."
$release = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest"
$asset = $release.assets | Where-Object { $_.name -eq "ChaChing.exe" } | Select-Object -First 1
if (-not $asset) { throw "ChaChing.exe asset not found in release $($release.tag_name)" }
Write-Host ("Latest: {0} ({1:N1} MB)" -f $release.tag_name, ($asset.size / 1MB))

Get-Process -Name "ChaChing" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Stopping running instance (PID $($_.Id))..."
    Stop-Process -Id $_.Id -Force
}
Start-Sleep -Seconds 1

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

Write-Host "Downloading ChaChing.exe ..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $ExePath -UseBasicParsing

$wsh = New-Object -ComObject WScript.Shell

$desktop = Join-Path $env:USERPROFILE "Desktop\ChaChing.lnk"
if (-not (Test-Path $desktop)) {
    $lnk = $wsh.CreateShortcut($desktop)
    $lnk.TargetPath = $ExePath
    $lnk.WorkingDirectory = $InstallDir
    $lnk.Description = "Cha-Ching Payment Notifications"
    $lnk.Save()
    Write-Host "Created Desktop shortcut"
}

$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\ChaChing.lnk"
if (-not (Test-Path $startup)) {
    $lnk = $wsh.CreateShortcut($startup)
    $lnk.TargetPath = $ExePath
    $lnk.WorkingDirectory = $InstallDir
    $lnk.Description = "Cha-Ching Payment Notifications"
    $lnk.Save()
    Write-Host "Created Startup shortcut (runs at login)"
}

Write-Host "Launching ChaChing ..."
Start-Process $ExePath

Write-Host ""
Write-Host "Done. Re-run this script any time to update to the latest release." -ForegroundColor Green
