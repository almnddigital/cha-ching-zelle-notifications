import base64
import json
import os
import tempfile


_FORMAT = "cha-ching-dpapi-v1"


def _win32crypt():
    if os.name != "nt":
        return None
    try:
        import win32crypt
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for Cha-Ching secure storage.") from exc
    return win32crypt


def _protect(value):
    win32crypt = _win32crypt()
    if not win32crypt:
        return value
    return win32crypt.CryptProtectData(
        value.encode("utf-8"),
        "Cha-Ching",
        None,
        None,
        None,
        0,
    )[1]


def _unprotect(value):
    win32crypt = _win32crypt()
    if not win32crypt:
        return value.decode("utf-8")
    return win32crypt.CryptUnprotectData(value, None, None, None, 0)[1].decode(
        "utf-8"
    )


def _encrypted_payload(data):
    raw = json.dumps(data, indent=2).encode("utf-8")
    return {
        "format": _FORMAT,
        "data": base64.b64encode(_protect(raw.decode("utf-8"))).decode("ascii"),
    }


def save_json(path, data):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    payload = _encrypted_payload(data) if os.name == "nt" else data
    fd, temp_path = tempfile.mkstemp(prefix=".chaching-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, dict) and payload.get("format") == _FORMAT:
        encrypted = base64.b64decode(payload["data"])
        return json.loads(_unprotect(encrypted))

    if os.name == "nt":
        save_json(path, payload)
    return payload
