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


class HistoryReadError(RuntimeError):
    pass


def _read_json_unlocked(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        return secure_storage.load_json(path)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        raise HistoryReadError(
            f"Could not read {os.path.basename(path)}. The existing file was not changed."
        ) from exc


def _read_unlocked(path):
    data = _read_json_unlocked(path, [])
    if not isinstance(data, list):
        raise HistoryReadError(
            f"Could not read {os.path.basename(path)}. The existing file was not changed."
        )
    return data


def _write_unlocked(path, records):
    secure_storage.save_json(path, records)


def load(path=HISTORY_FILE):
    with _LOCK:
        return _read_unlocked(path)


def _add_unlocked(name, amount, received_at, path, source_id, sender_email):
    record = {
        "received_at": received_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "name": (name or "Unknown sender").strip(),
        "amount": (amount or "Unknown amount").strip(),
    }
    if source_id is not None:
        record["source_id"] = str(source_id)
    if sender_email:
        record["sender_email"] = str(sender_email).strip()

    records = _read_unlocked(path)
    if source_id is not None:
        source_id = str(source_id)
        for existing in records:
            if existing.get("source_id") == source_id:
                changed = False
                if (
                    existing.get("name") in (None, "", "Unknown sender")
                    and record["name"] != "Unknown sender"
                ):
                    existing["name"] = record["name"]
                    changed = True
                if record.get("sender_email") and not existing.get("sender_email"):
                    existing["sender_email"] = record["sender_email"]
                    changed = True
                if (
                    existing.get("amount") in (None, "", "Unknown amount")
                    and record["amount"] != "Unknown amount"
                ):
                    existing["amount"] = record["amount"]
                    changed = True
                if changed:
                    _write_unlocked(path, records)
                return existing, False
    records.insert(0, record)
    _write_unlocked(path, records)
    return record, True


def add(
    name,
    amount,
    received_at=None,
    path=HISTORY_FILE,
    source_id=None,
    sender_email=None,
):
    with _LOCK:
        record, _ = _add_unlocked(
            name,
            amount,
            received_at,
            path,
            source_id,
            sender_email,
        )
    return record


def add_if_new(
    name,
    amount,
    received_at=None,
    source_id=None,
    path=HISTORY_FILE,
    sender_email=None,
):
    with _LOCK:
        _, inserted = _add_unlocked(
            name,
            amount,
            received_at,
            path,
            source_id,
            sender_email,
        )
    return inserted


def _record_from_mapping(value):
    record = {
        "received_at": value.get("received_at")
        or datetime.now().astimezone().isoformat(timespec="seconds"),
        "name": (value.get("name") or "Unknown sender").strip(),
        "amount": (value.get("amount") or "Unknown amount").strip(),
    }
    for field in ("source_id", "sender_email", "gmail_account"):
        if value.get(field):
            record[field] = str(value[field]).strip()
    return record


def _merge_record(existing, incoming):
    changed = False
    for field, unknown in (
        ("name", "Unknown sender"),
        ("amount", "Unknown amount"),
        ("sender_email", None),
        ("gmail_account", None),
    ):
        if existing.get(field) in (None, "", unknown) and incoming.get(field):
            if incoming.get(field) != unknown:
                existing[field] = incoming[field]
                changed = True
    return changed


def add_many(values, path=HISTORY_FILE):
    with _LOCK:
        records = _read_unlocked(path)
        by_source = {
            record.get("source_id"): record
            for record in records
            if record.get("source_id")
        }
        inserted = 0
        changed = False
        for value in values:
            incoming = _record_from_mapping(value)
            source_id = incoming.get("source_id")
            existing = by_source.get(source_id) if source_id else None
            if existing:
                changed = _merge_record(existing, incoming) or changed
                continue
            records.append(incoming)
            if source_id:
                by_source[source_id] = incoming
            inserted += 1
            changed = True
        if changed:
            records.sort(key=lambda record: record.get("received_at") or "", reverse=True)
            _write_unlocked(path, records)
    return inserted


def replace_gmail_records(values, path=HISTORY_FILE):
    replacements = [_record_from_mapping(value) for value in values]
    with _LOCK:
        records = [
            record
            for record in _read_unlocked(path)
            if not str(record.get("source_id", "")).startswith("gmail:")
        ]
        records.extend(replacements)
        records.sort(key=lambda record: record.get("received_at") or "", reverse=True)
        _write_unlocked(path, records)
    return len(replacements)


def gmail_record_count(path=HISTORY_FILE):
    with _LOCK:
        return sum(
            str(record.get("source_id", "")).startswith("gmail:")
            for record in _read_unlocked(path)
        )


def load_backfill_state(path=BACKFILL_STATE_FILE):
    with _LOCK:
        data = _read_json_unlocked(path)
    if data is not None and not isinstance(data, dict):
        raise HistoryReadError(
            f"Could not read {os.path.basename(path)}. The existing file was not changed."
        )
    return data


def mark_backfill_complete(
    length,
    scanned_count,
    imported_count,
    path=BACKFILL_STATE_FILE,
    gmail_account=None,
):
    state = {
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "length": length,
        "scanned_count": scanned_count,
        "imported_count": imported_count,
    }
    if gmail_account:
        state["gmail_account"] = gmail_account.strip().lower()
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
