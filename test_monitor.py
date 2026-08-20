import sys
import threading
import types
import unittest
from datetime import datetime, timezone


class FakeAddress:
    def __init__(self, host, mailbox="sender"):
        self.host = host
        self.mailbox = mailbox


class FakeEnvelope:
    def __init__(self, subject, host, received_at, mailbox="sender"):
        self.subject = subject
        self.from_ = [FakeAddress(host, mailbox)]
        self.date = received_at


class FakeIMAPClient:
    last_search = None

    def __init__(self, host, ssl):
        self.host = host
        self.ssl = ssl

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def login(self, gmail, app_password):
        self.credentials = (gmail, app_password)

    def select_folder(self, folder):
        self.folder = folder
        return {b"UIDVALIDITY": 42}

    def logout(self):
        pass

    def search(self, criteria):
        FakeIMAPClient.last_search = criteria
        return [1, 2, 3, 4]

    def fetch(self, uids, fields):
        envelopes = {
            1: FakeEnvelope(
                "Received $45.00 from Maria Lopez with Zelle",
                "notifications.chase.com",
                datetime(2026, 8, 13, 16, 30, tzinfo=timezone.utc),
            ),
            2: FakeEnvelope(
                "Weekly newsletter",
                "example.com",
                datetime(2026, 8, 13, 16, 31, tzinfo=timezone.utc),
            ),
            3: FakeEnvelope(
                "Payment received",
                "notifications.chase.com",
                datetime(2026, 8, 13, 16, 32, tzinfo=timezone.utc),
            ),
            4: FakeEnvelope(
                "Your Chase credit card statement is ready",
                "chase.com",
                datetime(2026, 8, 13, 16, 33, tzinfo=timezone.utc),
                mailbox="no.reply.alerts",
            ),
        }
        if fields == ["ENVELOPE"]:
            return {uid: {b"ENVELOPE": envelopes[uid]} for uid in uids}
        if fields == ["BODY[]"]:
            bodies = {
                3: b"Maria Lopez sent you money with Zelle. Amount $30.00",
                4: b"Your payment due is $300.00. Use Zelle to send money securely.",
            }
            return {uid: {b"BODY[]": bodies[uid]} for uid in uids}
        raise AssertionError(fields)


sys.modules["imapclient"] = types.SimpleNamespace(IMAPClient=FakeIMAPClient)
import monitor


class RetryingIMAPClient(FakeIMAPClient):
    failures_remaining = 1

    def fetch(self, uids, fields):
        if fields == ["BODY[]"] and RetryingIMAPClient.failures_remaining:
            RetryingIMAPClient.failures_remaining -= 1
            raise monitor.imaplib.IMAP4.abort("socket error: EOF")
        return super().fetch(uids, fields)


class MonitorBackfillTests(unittest.TestCase):
    def test_one_year_backfill_filters_and_parses_payments(self):
        records = monitor.fetch_historical_payments("gmail", "password", "1 year")

        self.assertEqual(FakeIMAPClient.last_search[0], "SINCE")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["name"], "Maria Lopez")
        self.assertEqual(records[0]["amount"], "$45.00")
        self.assertNotIn("sender_email", records[0])
        self.assertIsNone(records[0]["payer_email"])
        self.assertIsNone(records[0]["payer_phone"])
        self.assertEqual(records[1]["amount"], "$30.00")
        self.assertEqual(records[1]["source_id"], "gmail:gmail:42:3")
        self.assertTrue(all(record["amount"] != "Unknown amount" for record in records))

    def test_max_backfill_searches_for_zelle_text(self):
        monitor.fetch_historical_payments("gmail", "password", "Max")

        self.assertEqual(FakeIMAPClient.last_search, ["TEXT", "Zelle"])

    def test_bank_domain_without_zelle_marker_is_rejected(self):
        self.assertFalse(
            monitor._is_zelle(
                "Your statement is ready",
                "notifications.chase.com",
                "Balance $300.00",
            )
        )

    def test_generic_chase_alert_is_not_a_zelle_payment(self):
        self.assertFalse(
            monitor._is_valid_payment(
                "Payment received",
                "chase.com",
                "Your credit card payment was received. Amount $300.00. Use Zelle to send money.",
                "$300.00",
            )
        )

    def test_payment_without_an_amount_is_rejected(self):
        self.assertFalse(
            monitor._is_valid_payment(
                "Zelle payment received",
                "chase.com",
                "Maria Lopez sent you money with Zelle.",
                None,
            )
        )

    def test_payer_email_is_extracted_from_payment_text(self):
        env = FakeEnvelope(
            "Payment received",
            "chase.com",
            datetime(2026, 8, 13, 16, 34, tzinfo=timezone.utc),
            mailbox="no.reply.alerts",
        )

        name, amount, body, payer_email, payer_phone = monitor._parse_envelope(
            env,
            b"payer@example.com sent you money with Zelle. Amount $25.00",
        )

        self.assertIsNone(name)
        self.assertEqual(amount, "$25.00")
        self.assertIn("Zelle", body)
        self.assertEqual(payer_email, "payer@example.com")
        self.assertIsNone(payer_phone)

    def test_payer_phone_is_extracted_when_name_and_email_are_missing(self):
        env = FakeEnvelope(
            "Payment received",
            "chase.com",
            datetime(2026, 8, 13, 16, 35, tzinfo=timezone.utc),
        )

        name, amount, _, payer_email, payer_phone = monitor._parse_envelope(
            env,
            b"(916) 555-1212 sent you money with Zelle. Amount $40.00",
        )

        self.assertIsNone(name)
        self.assertEqual(amount, "$40.00")
        self.assertIsNone(payer_email)
        self.assertEqual(payer_phone, "(916) 555-1212")

    def test_notification_or_monitored_email_cannot_be_the_payer(self):
        env = FakeEnvelope(
            "Payment received",
            "voguecleaners.co",
            datetime(2026, 8, 13, 16, 36, tzinfo=timezone.utc),
            mailbox="hello",
        )

        self.assertIsNone(
            monitor._exclude_notification_email(
                "hello@voguecleaners.co",
                env,
                "recipient@example.com",
            )
        )
        self.assertIsNone(
            monitor._exclude_notification_email(
                "recipient@example.com",
                env,
                "recipient@example.com",
            )
        )

    def test_domain_matching_requires_a_real_domain_boundary(self):
        self.assertFalse(monitor._trusted_sender("fakechase.com"))
        self.assertTrue(monitor._trusted_sender("email.notifications.chase.com"))

    def test_encoded_subject_is_decoded(self):
        encoded = "=?UTF-8?Q?Received_=2445.00_from_Mar=C3=ADa_with_Zelle?="
        self.assertIn("María", monitor._decode_header_text(encoded))

    def test_cursor_resumes_only_for_the_same_account_and_mailbox(self):
        cursor = {"gmail": "store@example.com", "uid_validity": 42, "last_uid": 16802}

        self.assertEqual(
            monitor._cursor_last_uid(cursor, "store@example.com", 42),
            16802,
        )
        self.assertIsNone(monitor._cursor_last_uid(cursor, "other@example.com", 42))
        self.assertIsNone(monitor._cursor_last_uid(cursor, "store@example.com", 43))

    def test_backfill_can_be_cancelled_without_returning_partial_records(self):
        cancel_event = threading.Event()
        cancel_event.set()

        with self.assertRaises(monitor.BackfillCancelled):
            monitor.fetch_historical_payments(
                "gmail",
                "password",
                "Max",
                cancel_event=cancel_event,
            )

    def test_backfill_reports_progress(self):
        progress = []

        monitor.fetch_historical_payments(
            "gmail",
            "password",
            "Max",
            on_progress=lambda scanned, total, validated: progress.append(
                (scanned, total, validated)
            ),
        )

        self.assertEqual(progress[-1], (4, 4, 2))

    def test_backfill_reconnects_after_connection_drop(self):
        RetryingIMAPClient.failures_remaining = 1
        original_client = monitor.IMAPClient
        monitor.IMAPClient = RetryingIMAPClient
        try:
            records = monitor.fetch_historical_payments("gmail", "password", "Max")
        finally:
            monitor.IMAPClient = original_client

        self.assertEqual(len(records), 2)
        self.assertEqual(RetryingIMAPClient.failures_remaining, 0)


if __name__ == "__main__":
    unittest.main()
