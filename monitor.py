"""
Email monitor — connects to Gmail via IMAP IDLE and calls `on_payment`
whenever a Zelle confirmation email is detected.

Parses both email subject and body to extract sender name and amount.
Handles Chase, Bank of America, Wells Fargo, and other bank formats.

Runs in a background thread. Auto-reconnects on connection drops.
"""

import re
import threading
import time
import email as email_lib
import html as html_lib

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
    re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+sent you money", re.IGNORECASE),
    re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+sent you\s+\$", re.IGNORECASE),
]

BODY_AMOUNT_PATTERN = re.compile(r"Amount[\s\S]{0,300}?\$([\d,]+\.?\d{0,2})", re.IGNORECASE)


def _is_zelle(subject, domain):
    if "zelle" in subject.lower():
        return True
    return any(d in domain.lower() for d in ZELLE_DOMAINS)


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
                    client.select_folder("INBOX")
                    self.on_status("connected")
                    backoff = 5
                    # Track ALL existing UIDs — catches read AND unread new emails
                    seen = set(client.search(["ALL"]))
                    while not self._stop_event.is_set():
                        client.idle()
                        responses = client.idle_check(timeout=IDLE_TIMEOUT)
                        client.idle_done()
                        if not responses:
                            continue
                        all_uids = set(client.search(["ALL"]))
                        new_uids = all_uids - seen
                        seen = all_uids
                        for uid in new_uids:
                            try:
                                data = client.fetch([uid], ["ENVELOPE", "BODY[]"])
                                env = data[uid][b"ENVELOPE"]
                                subject = (env.subject or b"").decode("utf-8", errors="replace")
                                domain = ""
                                if env.from_:
                                    domain = (env.from_[0].host or b"").decode("utf-8", errors="replace")
                                if not _is_zelle(subject, domain):
                                    continue
                                name, amount = _parse_subject(subject)
                                if not name or not amount:
                                    raw = data[uid][b"BODY[]"]
                                    bn, ba = _parse_body(raw)
                                    name = name or bn
                                    amount = amount or ba
                                self.on_payment(name, amount)
                            except Exception:
                                pass
            except Exception:
                if self._stop_event.is_set():
                    break
                self.on_status("reconnecting")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
        self.on_status("stopped")


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
