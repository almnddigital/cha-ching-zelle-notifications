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

    return {
        "version": tag.lstrip("vV"),
        "tag": tag,
        "download_url": asset["browser_download_url"],
    }


def _installed_exe_path():
    if not getattr(sys, "frozen", False):
        raise RuntimeError("One-click updates are available from the installed EXE.")
    return os.path.abspath(sys.executable)


def install_update(release):
    download_url = release.get("download_url", "")
    expected_prefix = f"https://github.com/{REPOSITORY}/releases/download/"
    if not download_url.startswith(expected_prefix):
        raise RuntimeError("The update download URL is not trusted.")

    exe_path = _installed_exe_path()
    script = r'''
param(
    [int]$PidToWait,
    [string]$ExePath,
    [string]$DownloadUrl
)

$ErrorActionPreference = "Stop"
$TempPath = "$ExePath.update"
Start-Sleep -Seconds 2
Wait-Process -Id $PidToWait -ErrorAction SilentlyContinue

try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $TempPath -UseBasicParsing
    Move-Item -LiteralPath $TempPath -Destination $ExePath -Force
    Start-Process -FilePath $ExePath
}
catch {
    Remove-Item -LiteralPath $TempPath -Force -ErrorAction SilentlyContinue
}
finally {
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
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
