"""
Email monitor — connects to Gmail via IMAP IDLE and calls `on_payment`
whenever a Zelle confirmation email is detected.

Parses both email subject and body to extract sender name and amount.
Handles Chase, Bank of America, Wells Fargo, and other bank formats.

Runs in a background thread. Auto-reconnects on connection drops.
"""

import imaplib
import logging
import re
import socket
import threading
import time
import email as email_lib
import html as html_lib
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from imapclient import IMAPClient

IMAP_HOST = "imap.gmail.com"
IDLE_TIMEOUT = 25 * 60  # 25 min — Gmail drops IDLE at ~30 min

ZELLE_DOMAINS = [
    "zellepay.com",
    "notifications.chase.com",
    "alerts.bankofamerica.com",
    "wellsfargo.com",
    "citibank.com",
    "usbank.com",
    "tdbank.com",
    "pnc.com",
    "chase.com",
]

SUBJECT_PATTERNS = [
    re.compile(r"received\s+(\$[\d,]+\.?\d*)\s+from\s+(.+?)\s+with\s+zelle", re.IGNORECASE),
    re.compile(r"^(.+?)\s+sent you\s+(\$[\d,]+\.?\d*)\s+with\s+zelle", re.IGNORECASE),
]

BODY_NAME_PATTERNS = [
    re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+sent you money"),
    re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+sent you\s+\$"),
]

BODY_AMOUNT_PATTERN = re.compile(r"Amount[\s\S]{0,300}?\$([\d,]+\.?\d{0,2})", re.IGNORECASE)
BACKFILL_YEARS = {"1 year": 1, "2 years": 2}
BACKFILL_RETRIES = 3
IMAP_RETRY_ERRORS = (imaplib.IMAP4.abort, OSError, socket.timeout)


def _is_zelle(subject, domain):
    if "zelle" in subject.lower():
        return True
    return any(d in domain.lower() for d in ZELLE_DOMAINS)


def _decode_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _envelope_received_at(env):
    value = getattr(env, "date", None)
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = parsedate_to_datetime(_decode_text(value))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().isoformat(timespec="seconds")


def _parse_subject(subject):
    m = SUBJECT_PATTERNS[0].search(subject)
    if m:
        return m.group(2).strip(), m.group(1)
    m = SUBJECT_PATTERNS[1].search(subject)
    if m:
        return m.group(1).strip(), m.group(2)
    return None, None


def _extract_text(raw_bytes):
    msg = email_lib.message_from_bytes(raw_bytes)
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                text = part.get_payload(decode=True).decode("utf-8", errors="replace")
                break
            elif ct == "text/html" and not text:
                html = part.get_payload(decode=True).decode("utf-8", errors="replace")
                text = re.sub(r"<[^>]+>", " ", html)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            raw = payload.decode("utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                text = re.sub(r"<[^>]+>", " ", raw)
            else:
                text = raw
    return html_lib.unescape(re.sub(r"\s+", " ", text))


def _parse_body(raw_bytes):
    text = _extract_text(raw_bytes)
    name = None
    for p in BODY_NAME_PATTERNS:
        m = p.search(text)
        if m:
            name = m.group(1).strip()
            break
    amount = None
    m = BODY_AMOUNT_PATTERN.search(text)
    if m:
        amount = "$" + m.group(1)
    return name, amount


def _parse_envelope(env, raw_bytes=None):
    subject = _decode_text(env.subject)
    name, amount = _parse_subject(subject)
    if (not name or not amount) and raw_bytes:
        body_name, body_amount = _parse_body(raw_bytes)
        name = name or body_name
        amount = amount or body_amount
    return name, amount


class Monitor:
    def __init__(self, gmail, app_password, on_payment, on_status):
        self.gmail = gmail
        self.app_password = app_password
        self.on_payment = on_payment
        self.on_status = on_status
        self._stop_event = threading.Event()

    def start(self):
        self._stop_event.clear()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        backoff = 5
        while not self._stop_event.is_set():
            try:
                self.on_status("connecting")
                with IMAPClient(IMAP_HOST, ssl=True) as client:
                    client.login(self.gmail, self.app_password)
                    folders = [f[2] for f in client.list_folders()]
                    logging.info(f"FOLDERS: {folders}")
                    client.select_folder("[Gmail]/All Mail")
                    self.on_status("connected")
                    backoff = 5
                    # Track ALL existing UIDs — catches read AND unread new emails
                    seen = set(client.search(["ALL"]))
                    logging.info(f"BASELINE: {len(seen)} existing UIDs")
                    while not self._stop_event.is_set():
                        client.idle()
                        responses = client.idle_check(timeout=IDLE_TIMEOUT)
                        client.idle_done()
                        logging.info(f"IDLE tick: {len(responses)} responses")
                        if not responses:
                            continue
                        all_uids = set(client.search(["ALL"]))
                        new_uids = all_uids - seen
                        seen = all_uids
                        logging.info(f"NEW UIDS: {sorted(new_uids)}")
                        for uid in new_uids:
                            try:
                                data = client.fetch([uid], ["ENVELOPE", "BODY[]"])
                                env = data[uid][b"ENVELOPE"]
                                subject = _decode_text(env.subject)
                                domain = ""
                                if env.from_:
                                    domain = _decode_text(env.from_[0].host)
                                matched = _is_zelle(subject, domain)
                                logging.info(f"UID {uid}: subj={subject!r} domain={domain!r} zelle={matched}")
                                if not matched:
                                    continue
                                name, amount = _parse_envelope(env, data[uid].get(b"BODY[]"))
                                logging.info(f"UID {uid}: parsed name={name!r} amount={amount!r}")
                                self.on_payment(
                                    name,
                                    amount,
                                    _envelope_received_at(env),
                                    f"gmail:{uid}",
                                )
                            except Exception as e:
                                logging.exception(f"UID {uid} failed: {e}")
            except Exception:
                if self._stop_event.is_set():
                    break
                self.on_status("reconnecting")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
        self.on_status("stopped")


def fetch_historical_payments(gmail, app_password, length):
    if length not in BACKFILL_YEARS and length != "Max":
        raise ValueError(f"Unsupported backfill length: {length}")

    criteria = ["ALL"]
    if length in BACKFILL_YEARS:
        since = date.today() - timedelta(days=365 * BACKFILL_YEARS[length])
        criteria = ["SINCE", since.strftime("%d-%b-%Y")]

    records = []
    client = IMAPClient(IMAP_HOST, ssl=True)

    def reconnect():
        nonlocal client
        try:
            client.logout()
        except Exception:
            pass
        time.sleep(1)
        client = IMAPClient(IMAP_HOST, ssl=True)
        client.login(gmail, app_password)
        client.select_folder("[Gmail]/All Mail")

    def retry(operation, label):
        for attempt in range(BACKFILL_RETRIES):
            try:
                return operation()
            except IMAP_RETRY_ERRORS as exc:
                if attempt == BACKFILL_RETRIES - 1:
                    raise
                logging.warning(
                    "BACKFILL: %s failed; reconnecting (%d/%d): %s",
                    label,
                    attempt + 1,
                    BACKFILL_RETRIES - 1,
                    exc,
                )
                reconnect()

    try:
        client.login(gmail, app_password)
        client.select_folder("[Gmail]/All Mail")
        uids = retry(lambda: client.search(criteria), "search")
        logging.info("BACKFILL: scanning %d messages", len(uids))
        for start in range(0, len(uids), 100):
            batch = uids[start : start + 100]
            envelopes = retry(
                lambda: client.fetch(batch, ["ENVELOPE"]),
                f"envelopes {start + 1}-{start + len(batch)}",
            )
            for uid in batch:
                data = envelopes.get(uid)
                if not data:
                    continue
                env = data[b"ENVELOPE"]
                subject = _decode_text(env.subject)
                domain = ""
                if env.from_:
                    domain = _decode_text(env.from_[0].host)
                if not _is_zelle(subject, domain):
                    continue

                name, amount = _parse_envelope(env)
                if not name or not amount:
                    body_data = retry(
                        lambda: client.fetch([uid], ["BODY[]"]),
                        f"body uid {uid}",
                    )
                    raw = body_data[uid].get(b"BODY[]")
                    name, amount = _parse_envelope(env, raw)

                records.append(
                    {
                        "name": name,
                        "amount": amount,
                        "received_at": _envelope_received_at(env),
                        "source_id": f"gmail:{uid}",
                    }
                )
            logging.info(
                "BACKFILL: scanned %d/%d messages",
                min(start + len(batch), len(uids)),
                len(uids),
            )
    finally:
        try:
            client.logout()
        except Exception:
            pass
    return records


def test_credentials(gmail, app_password):
    try:
        with IMAPClient(IMAP_HOST, ssl=True) as client:
            client.login(gmail, app_password)
            return True, "Connected successfully!"
    except Exception as e:
        msg = str(e)
        if "AUTHENTICATIONFAILED" in msg or "Invalid credentials" in msg:
            return False, "Wrong email or App Password. Double-check and try again."
        if "IMAP access disabled" in msg:
            return False, "IMAP is disabled in Gmail. Enable it in Gmail Settings."
        return False, f"Connection failed: {msg}"
