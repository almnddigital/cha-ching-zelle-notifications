"""
Email monitor — connects to Gmail via IMAP IDLE and calls `on_payment`
whenever a Zelle confirmation email is detected.

Parses both email subject and body to extract sender name and amount.
Handles Chase, Bank of America, Wells Fargo, and other bank formats.

Runs in a background thread. Auto-reconnects on connection drops.
"""

import imaplib
import logging
import os
import re
import socket
import threading
import time
import email as email_lib
import html as html_lib
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from imapclient import IMAPClient

import config
import secure_storage

IMAP_HOST = "imap.gmail.com"
IDLE_TIMEOUT = 25 * 60  # 25 min — Gmail drops IDLE at ~30 min

ZELLE_DOMAINS = {
    "zellepay.com",
    "notifications.chase.com",
    "alerts.bankofamerica.com",
    "wellsfargo.com",
    "citibank.com",
    "usbank.com",
    "tdbank.com",
    "pnc.com",
    "chase.com",
}

SUBJECT_PATTERNS = [
    re.compile(r"received\s+(\$[\d,]+(?:\.\d{1,2})?)\s+from\s+(.+?)\s+with\s+zelle", re.IGNORECASE),
    re.compile(r"^(.+?)\s+sent you\s+(\$[\d,]+(?:\.\d{1,2})?)\s+with\s+zelle", re.IGNORECASE),
]

EMAIL_VALUE = r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}"
PHONE_VALUE = r"(?:\+?1[\s().-]*)?(?:\(\d{3}\)|\d{3})[\s.-]*\d{3}[\s.-]*\d{4}"
NAME_VALUE = r"[A-Z][A-Z0-9&'’.\-]*(?:\s+[A-Z0-9][A-Z0-9&'’.\-]*){0,5}"

BODY_NAME_PATTERNS = [
    re.compile(
        rf"\bzelle\s*(?:®)?\s*payment\s+({NAME_VALUE})\s+sent you money",
        re.IGNORECASE,
    ),
    re.compile(rf"(?<![@.\w])({NAME_VALUE})\s+sent you money", re.IGNORECASE),
    re.compile(rf"(?<![@.\w])({NAME_VALUE})\s+sent you\s+\$", re.IGNORECASE),
    re.compile(
        rf"(?:sender|from)\s*:?\s*({NAME_VALUE})(?=\s+(?:amount|memo|sent)|\s*\$)",
        re.IGNORECASE,
    ),
]

BODY_EMAIL_PATTERNS = [
    re.compile(rf"({EMAIL_VALUE})\s+sent you(?: money|\s+\$)", re.IGNORECASE),
    re.compile(
        rf"(?:sender email|email address|sent by|from)\s*:?\s*({EMAIL_VALUE})",
        re.IGNORECASE,
    ),
]

BODY_PHONE_PATTERNS = [
    re.compile(rf"({PHONE_VALUE})\s+sent you(?: money|\s+\$)", re.IGNORECASE),
    re.compile(
        rf"(?:sender phone|phone number|mobile number|sent by|from)\s*:?\s*({PHONE_VALUE})",
        re.IGNORECASE,
    ),
]

BODY_AMOUNT_PATTERNS = [
    re.compile(r"Amount[\s\S]{0,120}?\$([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE),
    re.compile(r"sent you[\s\S]{0,80}?\$([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE),
    re.compile(r"payment(?: of| for)?[\s\S]{0,80}?\$([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE),
]
ZELLE_MARKER_PATTERN = re.compile(r"\bzelle(?:®)?\b", re.IGNORECASE)
BODY_PAYMENT_EVENT_PATTERNS = [
    re.compile(
        rf"(?:{NAME_VALUE}|{EMAIL_VALUE}|{PHONE_VALUE})\s+sent you(?: money|\s+\$)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"you(?:'ve| have)? received(?: money|\s+\$[\d,]+(?:\.\d{{1,2}})?)[\s\S]{{0,160}}?from\s+(?:{NAME_VALUE}|{EMAIL_VALUE}|{PHONE_VALUE})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"payment received[\s\S]{{0,300}}?(?:sender|from)\s*:?\s*(?:{NAME_VALUE}|{EMAIL_VALUE}|{PHONE_VALUE})[\s\S]{{0,120}}?amount\s*:?\s*\$",
        re.IGNORECASE,
    ),
]
BACKFILL_YEARS = {"1 year": 1, "2 years": 2}
BACKFILL_RETRIES = 3
IMAP_RETRY_ERRORS = (imaplib.IMAP4.abort, OSError, socket.timeout)
MONITOR_STATE_FILE = os.path.join(config.CONFIG_DIR, "monitor_state.json")
_CURSOR_LOCK = threading.Lock()


class BackfillCancelled(RuntimeError):
    pass


def _trusted_sender(domain):
    normalized = (domain or "").strip().lower().rstrip(".")
    return any(
        normalized == allowed or normalized.endswith("." + allowed)
        for allowed in ZELLE_DOMAINS
    )


def _is_zelle(subject, domain, body_text=""):
    return _trusted_sender(domain) and bool(
        ZELLE_MARKER_PATTERN.search(f"{subject}\n{body_text}")
    )


def _is_candidate(subject, domain):
    return _trusted_sender(domain) or bool(ZELLE_MARKER_PATTERN.search(subject))


def _is_valid_payment(subject, domain, body_text, amount):
    if not amount or not _is_zelle(subject, domain, body_text):
        return False
    _, subject_amount = _parse_subject(subject)
    return bool(
        subject_amount
        or any(pattern.search(body_text) for pattern in BODY_PAYMENT_EVENT_PATTERNS)
    )


def _decode_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _decode_header_text(value):
    raw = _decode_text(value)
    try:
        return str(make_header(decode_header(raw)))
    except (LookupError, UnicodeError):
        return raw


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


def _envelope_sender_email(env):
    addresses = getattr(env, "from_", None) or []
    if not addresses:
        return None
    address = addresses[0]
    mailbox = _decode_text(getattr(address, "mailbox", None)).strip()
    host = _decode_text(getattr(address, "host", None)).strip()
    if mailbox and host:
        return f"{mailbox}@{host}"
    return None


def _authenticated_original_sender_domain(raw_bytes):
    if not raw_bytes:
        return None
    msg = email_lib.message_from_bytes(raw_bytes)
    original_sender = None
    for header in ("X-Original-Sender", "X-Original-From"):
        _, address = parseaddr(msg.get(header, ""))
        if address:
            original_sender = address.strip().lower()
            break
    if not original_sender or "@" not in original_sender:
        return None
    domain = original_sender.rsplit("@", 1)[1].rstrip(".")
    if not _trusted_sender(domain):
        return None

    authentication = " ".join(
        msg.get_all("X-Original-Authentication-Results", [])
        + msg.get_all("ARC-Authentication-Results", [])
    )
    receiving_authentication = " ".join(msg.get_all("Authentication-Results", []))
    escaped_domain = re.escape(domain)
    dkim_passed = re.search(
        rf"\bdkim=pass\b[^;]*(?:header\.i=@|dkdomain=){escaped_domain}\b",
        authentication,
        re.IGNORECASE,
    )
    dmarc_passed = re.search(
        rf"\bdmarc=pass\b[^;]*(?:header\.from=|fromdomain=){escaped_domain}\b",
        authentication,
        re.IGNORECASE,
    )
    arc_passed = re.search(r"\barc=pass\b", receiving_authentication, re.IGNORECASE)
    arc_domain_passed = re.search(
        rf"(?:\bdkim=pass\b[^;)]*dkdomain={escaped_domain}\b|"
        rf"\bdmarc=pass\b[^;)]*fromdomain={escaped_domain}\b)",
        receiving_authentication,
        re.IGNORECASE,
    )
    return domain if (dkim_passed or dmarc_passed) and arc_passed and arc_domain_passed else None


def _classify_payer_identity(value):
    identity = (value or "").strip().strip(".,;:")
    if not identity:
        return None, None, None
    if re.fullmatch(EMAIL_VALUE, identity, re.IGNORECASE):
        return None, identity, None
    if re.fullmatch(PHONE_VALUE, identity, re.IGNORECASE):
        return None, None, identity
    return identity, None, None


def _exclude_notification_email(payer_email, env, gmail):
    if not payer_email:
        return None
    normalized = payer_email.strip().lower()
    excluded = {
        value.strip().lower()
        for value in (_envelope_sender_email(env), gmail)
        if value and value.strip()
    }
    return None if normalized in excluded else payer_email.strip()


def _parse_subject(subject):
    m = SUBJECT_PATTERNS[0].search(subject)
    if m:
        return m.group(2).strip(), m.group(1)
    m = SUBJECT_PATTERNS[1].search(subject)
    if m:
        return m.group(1).strip(), m.group(2)
    return None, None


def _decode_part(part):
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _extract_text(raw_bytes):
    msg = email_lib.message_from_bytes(raw_bytes)
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                text = _decode_part(part)
                break
            elif ct == "text/html" and not text:
                html = _decode_part(part)
                text = re.sub(r"<[^>]+>", " ", html)
    else:
        raw = _decode_part(msg)
        if msg.get_content_type() == "text/html":
            text = re.sub(r"<[^>]+>", " ", raw)
        else:
            text = raw
    return html_lib.unescape(re.sub(r"\s+", " ", text))


def _parse_body(raw_bytes):
    text = _extract_text(raw_bytes)
    name = None
    payer_email = None
    payer_phone = None
    for p in BODY_NAME_PATTERNS:
        m = p.search(text)
        if m:
            name, payer_email, payer_phone = _classify_payer_identity(m.group(1))
            break
    amount = None
    for pattern in BODY_AMOUNT_PATTERNS:
        m = pattern.search(text)
        if m:
            amount = "$" + m.group(1)
            break
    for pattern in BODY_EMAIL_PATTERNS:
        m = pattern.search(text)
        if m:
            payer_email = payer_email or m.group(1).strip()
            break
    for pattern in BODY_PHONE_PATTERNS:
        m = pattern.search(text)
        if m:
            payer_phone = payer_phone or m.group(1).strip()
            break
    return name, amount, text, payer_email, payer_phone


def _parse_envelope(env, raw_bytes=None):
    subject = _decode_header_text(env.subject)
    identity, amount = _parse_subject(subject)
    name, payer_email, payer_phone = _classify_payer_identity(identity)
    body_text = ""
    if (not name or not amount) and raw_bytes:
        body_name, body_amount, body_text, body_email, body_phone = _parse_body(raw_bytes)
        name = name or body_name
        amount = amount or body_amount
        payer_email = payer_email or body_email
        payer_phone = payer_phone or body_phone
    elif raw_bytes:
        body_text = _extract_text(raw_bytes)
    return name, amount, body_text, payer_email, payer_phone


def _uid_validity(folder_info):
    if not folder_info:
        return 0
    for key in (b"UIDVALIDITY", "UIDVALIDITY"):
        if key in folder_info:
            return int(folder_info[key])
    return 0


def _source_id(gmail, uid_validity, uid):
    return f"gmail:{gmail.strip().lower()}:{uid_validity}:{uid}"


def _load_cursor():
    with _CURSOR_LOCK:
        try:
            state = secure_storage.load_json(MONITOR_STATE_FILE)
        except Exception:
            logging.exception("Could not read Gmail monitor cursor; starting a new baseline")
            return None
    return state if isinstance(state, dict) else None


def _save_cursor(gmail, uid_validity, last_uid):
    state = {
        "gmail": gmail.strip().lower(),
        "uid_validity": int(uid_validity),
        "last_uid": int(last_uid),
    }
    with _CURSOR_LOCK:
        secure_storage.save_json(MONITOR_STATE_FILE, state)


def _cursor_last_uid(cursor, gmail, uid_validity):
    if not cursor:
        return None
    if cursor.get("gmail") != gmail.strip().lower():
        return None
    if int(cursor.get("uid_validity", -1)) != int(uid_validity):
        return None
    return int(cursor.get("last_uid", 0))


class Monitor:
    def __init__(self, gmail, app_password, on_payment, on_status):
        self.gmail = gmail
        self.app_password = app_password
        self.on_payment = on_payment
        self.on_status = on_status
        self._stop_event = threading.Event()
        self._thread = None
        self._client = None
        self._client_lock = threading.Lock()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        with self._client_lock:
            client = self._client
        if client:
            try:
                client.shutdown()
            except Exception:
                try:
                    client._imap.shutdown()
                except Exception:
                    pass
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    def _set_client(self, client):
        with self._client_lock:
            self._client = client

    def _process_uid(self, client, uid, uid_validity):
        data = client.fetch([uid], ["ENVELOPE"])
        env = data[uid][b"ENVELOPE"]
        subject = _decode_header_text(env.subject)
        domain = ""
        if env.from_:
            domain = _decode_text(env.from_[0].host)
        if not _is_candidate(subject, domain):
            return

        name, amount, body_text, payer_email, payer_phone = _parse_envelope(env)
        if not amount or not _is_zelle(subject, domain, body_text):
            body_data = client.fetch([uid], ["BODY[]"])
            raw = body_data[uid].get(b"BODY[]")
            name, amount, body_text, payer_email, payer_phone = _parse_envelope(env, raw)
            domain = _authenticated_original_sender_domain(raw) or domain
        if not _is_valid_payment(subject, domain, body_text, amount):
            logging.info("UID %s: rejected bank notification", uid)
            return

        payer_email = _exclude_notification_email(payer_email, env, self.gmail)
        logging.info("UID %s: validated Zelle payment", uid)
        self.on_payment(
            name,
            amount,
            _envelope_received_at(env),
            _source_id(self.gmail, uid_validity, uid),
            payer_email,
            payer_phone,
        )

    def _run(self):
        backoff = 5
        while not self._stop_event.is_set():
            try:
                self.on_status("connecting")
                with IMAPClient(IMAP_HOST, ssl=True) as client:
                    self._set_client(client)
                    client.login(self.gmail, self.app_password)
                    folder_info = client.select_folder("[Gmail]/All Mail")
                    uid_validity = _uid_validity(folder_info)
                    self.on_status("connected")
                    backoff = 5
                    cursor = _load_cursor()
                    last_uid = _cursor_last_uid(cursor, self.gmail, uid_validity)
                    if last_uid is None:
                        existing = client.search(["ALL"])
                        last_uid = max(existing, default=0)
                        _save_cursor(self.gmail, uid_validity, last_uid)
                        logging.info("Established Gmail monitor baseline")
                    while not self._stop_event.is_set():
                        new_uids = client.search(["UID", f"{last_uid + 1}:*"])
                        for uid in sorted(uid for uid in new_uids if uid > last_uid):
                            self._process_uid(client, uid, uid_validity)
                            last_uid = uid
                            _save_cursor(self.gmail, uid_validity, last_uid)
                        if self._stop_event.is_set():
                            break
                        client.idle()
                        responses = client.idle_check(timeout=IDLE_TIMEOUT)
                        client.idle_done()
            except Exception:
                if self._stop_event.is_set():
                    break
                logging.exception("Gmail monitor connection failed")
                self.on_status("reconnecting")
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, 60)
            finally:
                self._set_client(None)
        self.on_status("stopped")


def fetch_historical_payments(
    gmail,
    app_password,
    length,
    on_progress=None,
    cancel_event=None,
):
    if length not in BACKFILL_YEARS and length != "Max":
        raise ValueError(f"Unsupported backfill length: {length}")

    criteria = ["TEXT", "Zelle"]
    if length in BACKFILL_YEARS:
        since = date.today() - timedelta(days=365 * BACKFILL_YEARS[length])
        criteria = ["SINCE", since.strftime("%d-%b-%Y"), "TEXT", "Zelle"]

    records = []
    client = IMAPClient(IMAP_HOST, ssl=True)
    uid_validity = 0

    def reconnect():
        nonlocal client, uid_validity
        try:
            client.logout()
        except Exception:
            pass
        time.sleep(1)
        client = IMAPClient(IMAP_HOST, ssl=True)
        client.login(gmail, app_password)
        folder_info = client.select_folder("[Gmail]/All Mail")
        uid_validity = _uid_validity(folder_info)

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
        folder_info = client.select_folder("[Gmail]/All Mail")
        uid_validity = _uid_validity(folder_info)
        uids = retry(lambda: client.search(criteria), "search")
        logging.info("BACKFILL: scanning %d messages", len(uids))
        for start in range(0, len(uids), 100):
            if cancel_event and cancel_event.is_set():
                raise BackfillCancelled("Import cancelled. Existing history was not changed.")
            batch = uids[start : start + 100]
            envelopes = retry(
                lambda: client.fetch(batch, ["ENVELOPE"]),
                f"envelopes {start + 1}-{start + len(batch)}",
            )
            for uid in batch:
                if cancel_event and cancel_event.is_set():
                    raise BackfillCancelled(
                        "Import cancelled. Existing history was not changed."
                    )
                data = envelopes.get(uid)
                if not data:
                    continue
                env = data[b"ENVELOPE"]
                subject = _decode_header_text(env.subject)
                domain = ""
                if env.from_:
                    domain = _decode_text(env.from_[0].host)
                if not _is_candidate(subject, domain):
                    continue

                name, amount, body_text, payer_email, payer_phone = _parse_envelope(env)
                if not amount or not _is_zelle(subject, domain, body_text):
                    body_data = retry(
                        lambda: client.fetch([uid], ["BODY[]"]),
                        f"body uid {uid}",
                    )
                    raw = body_data[uid].get(b"BODY[]")
                    name, amount, body_text, payer_email, payer_phone = _parse_envelope(env, raw)
                    domain = _authenticated_original_sender_domain(raw) or domain
                if not _is_valid_payment(subject, domain, body_text, amount):
                    continue
                payer_email = _exclude_notification_email(payer_email, env, gmail)

                records.append(
                    {
                        "name": name,
                        "amount": amount,
                        "received_at": _envelope_received_at(env),
                        "source_id": _source_id(gmail, uid_validity, uid),
                        "payer_email": payer_email,
                        "payer_phone": payer_phone,
                        "gmail_account": gmail.strip().lower(),
                    }
                )
            logging.info(
                "BACKFILL: scanned %d/%d messages",
                min(start + len(batch), len(uids)),
                len(uids),
            )
            if on_progress:
                on_progress(
                    min(start + len(batch), len(uids)),
                    len(uids),
                    len(records),
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
