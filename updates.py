import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

from version import APP_VERSION


REPOSITORY = "almnddigital/cha-ching-zelle-notifications"
RELEASES_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
EXE_NAME = "ChaChing.exe"
CHECKSUM_NAME = "ChaChing.exe.sha256"


def _version_tuple(value):
    match = re.search(r"\d+(?:\.\d+)*", value or "")
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(0).split("."))


def check_for_update():
    request = urllib.request.Request(
        RELEASES_URL,
        headers={"User-Agent": "Cha-Ching-Payment-Notifications"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        release = json.load(response)

    if release.get("draft") or release.get("prerelease"):
        return None
    tag = release.get("tag_name", "")
    if _version_tuple(tag) <= _version_tuple(APP_VERSION):
        return None

    asset = next(
        (item for item in release.get("assets", []) if item.get("name") == EXE_NAME),
        None,
    )
    if not asset or not asset.get("browser_download_url"):
        return None
    checksum = next(
        (item for item in release.get("assets", []) if item.get("name") == CHECKSUM_NAME),
        None,
    )
    if not checksum or not checksum.get("browser_download_url"):
        return None

    return {
        "version": tag.lstrip("vV"),
        "tag": tag,
        "download_url": asset["browser_download_url"],
        "checksum_url": checksum["browser_download_url"],
    }


def _installed_exe_path():
    if not getattr(sys, "frozen", False):
        raise RuntimeError("One-click updates are available from the installed EXE.")
    return os.path.abspath(sys.executable)


def install_update(release):
    download_url = release.get("download_url", "")
    checksum_url = release.get("checksum_url", "")
    expected_prefix = f"https://github.com/{REPOSITORY}/releases/download/"
    if not download_url.startswith(expected_prefix) or not checksum_url.startswith(
        expected_prefix
    ):
        raise RuntimeError("The update download URL is not trusted.")

    exe_path = _installed_exe_path()
    script = r'''
param(
    [int]$PidToWait,
    [string]$ExePath,
    [string]$DownloadUrl,
    [string]$ChecksumUrl
)

$ErrorActionPreference = "Stop"
$TempPath = "$ExePath.update"
$ChecksumPath = "$ExePath.update.sha256"
$BackupPath = "$ExePath.bak"
$ErrorLog = Join-Path $env:APPDATA "ChaChing\update-error.log"
$BackupCreated = $false
Start-Sleep -Seconds 2
Wait-Process -Id $PidToWait -ErrorAction SilentlyContinue

try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $TempPath -UseBasicParsing
    Invoke-WebRequest -Uri $ChecksumUrl -OutFile $ChecksumPath -UseBasicParsing
    $ExpectedHash = ((Get-Content -LiteralPath $ChecksumPath -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
    if ($ExpectedHash -notmatch "^[a-f0-9]{64}$") {
        throw "The release checksum is invalid."
    }
    $ActualHash = (Get-FileHash -LiteralPath $TempPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualHash -ne $ExpectedHash) {
        throw "The downloaded update failed checksum verification."
    }
    Copy-Item -LiteralPath $ExePath -Destination $BackupPath -Force
    $BackupCreated = $true
    Move-Item -LiteralPath $TempPath -Destination $ExePath -Force
    Start-Process -FilePath $ExePath
}
catch {
    if ($BackupCreated -and (Test-Path -LiteralPath $BackupPath)) {
        Copy-Item -LiteralPath $BackupPath -Destination $ExePath -Force
    }
    if (Test-Path -LiteralPath $ExePath) {
        Start-Process -FilePath $ExePath -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $ErrorLog) | Out-Null
    $_ | Out-String | Set-Content -LiteralPath $ErrorLog
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "The update failed and the previous version was restored. Try again later.",
        "Cha-Ching Update Failed",
        "OK",
        "Error"
    ) | Out-Null
    Remove-Item -LiteralPath $TempPath -Force -ErrorAction SilentlyContinue
}
finally {
    Remove-Item -LiteralPath $ChecksumPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
}
'''
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".ps1",
        prefix="chaching-update-",
        delete=False,
        encoding="utf-8",
    ) as f:
        script_path = f.name
        f.write(script)

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            script_path,
            "-PidToWait",
            str(os.getpid()),
            "-ExePath",
            exe_path,
            "-DownloadUrl",
            download_url,
            "-ChecksumUrl",
            checksum_url,
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
