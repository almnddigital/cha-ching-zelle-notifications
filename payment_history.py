import os
import re
import threading
from datetime import datetime
from decimal import Decimal, InvalidOperation

import config
import secure_storage


HISTORY_FILE = os.path.join(config.CONFIG_DIR, "payments.json")
BACKFILL_STATE_FILE = os.path.join(config.CONFIG_DIR, "backfill.json")
_LOCK = threading.Lock()
_AMOUNT_PATTERN = re.compile(r"^\$([\d,]+(?:\.\d{1,2})?)$")


def _read_json_unlocked(path):
    if not os.path.exists(path):
        return []
    try:
        return secure_storage.load_json(path)
    except (OSError, ValueError, TypeError, RuntimeError):
        return []


def _read_unlocked(path):
    data = _read_json_unlocked(path)
    return data if isinstance(data, list) else []


def _write_unlocked(path, records):
    secure_storage.save_json(path, records)


def load(path=HISTORY_FILE):
    with _LOCK:
        return _read_unlocked(path)


def _add_unlocked(name, amount, received_at, path, source_id):
    record = {
        "received_at": received_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "name": (name or "Unknown sender").strip(),
        "amount": (amount or "Unknown amount").strip(),
    }
    if source_id is not None:
        record["source_id"] = str(source_id)

    records = _read_unlocked(path)
    if source_id is not None:
        source_id = str(source_id)
        for existing in records:
            if existing.get("source_id") == source_id:
                return existing, False
    records.insert(0, record)
    _write_unlocked(path, records)
    return record, True


def add(name, amount, received_at=None, path=HISTORY_FILE, source_id=None):
    with _LOCK:
        record, _ = _add_unlocked(name, amount, received_at, path, source_id)
    return record


def add_if_new(name, amount, received_at=None, source_id=None, path=HISTORY_FILE):
    with _LOCK:
        _, inserted = _add_unlocked(name, amount, received_at, path, source_id)
    return inserted


def load_backfill_state(path=BACKFILL_STATE_FILE):
    with _LOCK:
        data = _read_json_unlocked(path)
    return data if isinstance(data, dict) else None


def mark_backfill_complete(length, scanned_count, imported_count, path=BACKFILL_STATE_FILE):
    state = {
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "length": length,
        "scanned_count": scanned_count,
        "imported_count": imported_count,
    }
    with _LOCK:
        _write_unlocked(path, state)


def total_amount(records):
    total = Decimal("0")
    for record in records:
        amount = str(record.get("amount", ""))
        match = _AMOUNT_PATTERN.fullmatch(amount)
        if not match:
            continue
        try:
            total += Decimal(match.group(1).replace(",", ""))
        except InvalidOperation:
            continue
    return total
