import sys
import types
import unittest
from datetime import datetime, timezone


class FakeAddress:
    def __init__(self, host):
        self.host = host


class FakeEnvelope:
    def __init__(self, subject, host, received_at):
        self.subject = subject
        self.from_ = [FakeAddress(host)]
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

    def search(self, criteria):
        FakeIMAPClient.last_search = criteria
        return [1, 2, 3]

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
        }
        if fields == ["ENVELOPE"]:
            return {uid: {b"ENVELOPE": envelopes[uid]} for uid in uids}
        if fields == ["BODY[]"]:
            return {3: {b"BODY[]": b"Maria Lopez sent you money. Amount $30.00"}}
        raise AssertionError(fields)


sys.modules["imapclient"] = types.SimpleNamespace(IMAPClient=FakeIMAPClient)
import monitor


class MonitorBackfillTests(unittest.TestCase):
    def test_one_year_backfill_filters_and_parses_payments(self):
        records = monitor.fetch_historical_payments("gmail", "password", "1 year")

        self.assertEqual(FakeIMAPClient.last_search[0], "SINCE")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["name"], "Maria Lopez")
        self.assertEqual(records[0]["amount"], "$45.00")
        self.assertEqual(records[1]["amount"], "$30.00")
        self.assertEqual(records[1]["source_id"], "gmail:3")

    def test_max_backfill_searches_all_mail(self):
        monitor.fetch_historical_payments("gmail", "password", "Max")

        self.assertEqual(FakeIMAPClient.last_search, ["ALL"])


if __name__ == "__main__":
    unittest.main()
