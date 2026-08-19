"""
Config management — reads/writes to %APPDATA%\\ChaChing\\config.json
"""

import os

import secure_storage

CONFIG_DIR = os.path.join(os.getenv("APPDATA", "."), "ChaChing")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load():
    """Returns config dict or None if not configured yet."""
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        return secure_storage.load_json(CONFIG_FILE)
    except Exception:
        return None


def save(gmail, app_password, business_name=""):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    secure_storage.save_json(
        CONFIG_FILE,
        {
            "gmail": gmail.strip(),
            "app_password": app_password.strip(),
            "business_name": business_name.strip(),
        },
    )


def clear():
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
