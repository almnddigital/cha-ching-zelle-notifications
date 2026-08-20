import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import payment_history


class PaymentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp_dir.name) / "payments.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_persists_newest_first(self):
        payment_history.add("Maria Lopez", "$45.00", "2026-08-13T09:30:00-07:00", self.path)
        payment_history.add("Jon Kim", "$1,200.50", "2026-08-13T10:00:00-07:00", self.path)

        records = payment_history.load(self.path)

        self.assertEqual([record["name"] for record in records], ["Jon Kim", "Maria Lopez"])
        self.assertEqual(payment_history.total_amount(records), Decimal("1245.50"))

        with open(self.path, encoding="utf-8") as f:
            self.assertIsInstance(json.load(f), list)

    def test_missing_values_are_visible(self):
        payment_history.add(None, None, path=self.path)

        self.assertEqual(
            payment_history.load(self.path)[0],
            {
                "received_at": payment_history.load(self.path)[0]["received_at"],
                "name": "Unknown sender",
                "amount": "Unknown amount",
            },
        )

    def test_source_id_prevents_duplicate_imports(self):
        self.assertTrue(
            payment_history.add_if_new(
                "Maria Lopez",
                "$45.00",
                "2026-08-13T09:30:00-07:00",
                "gmail:123",
                self.path,
            )
        )
        self.assertFalse(
            payment_history.add_if_new(
                "Maria Lopez",
                "$45.00",
                "2026-08-13T09:30:00-07:00",
                "gmail:123",
                self.path,
            )
        )
        self.assertEqual(len(payment_history.load(self.path)), 1)

    def test_duplicate_import_fills_missing_sender_details(self):
        payment_history.add_if_new(
            "Unknown sender",
            "$45.00",
            "2026-08-13T09:30:00-07:00",
            "gmail:123",
            self.path,
        )
        payment_history.add_if_new(
            "Maria Lopez",
            "$45.00",
            "2026-08-13T09:30:00-07:00",
            "gmail:123",
            self.path,
            sender_email="sender@example.com",
        )

        record = payment_history.load(self.path)[0]
        self.assertEqual(record["name"], "Maria Lopez")
        self.assertEqual(record["sender_email"], "sender@example.com")

    def test_backfill_state_is_persisted(self):
        state_path = str(Path(self.temp_dir.name) / "backfill.json")
        payment_history.mark_backfill_complete("1 year", 8, 6, state_path)

        self.assertEqual(
            payment_history.load_backfill_state(state_path)["imported_count"],
            6,
        )

    def test_bulk_import_writes_all_records_once(self):
        inserted = payment_history.add_many(
            [
                {
                    "name": "Maria Lopez",
                    "amount": "$45.00",
                    "received_at": "2026-08-13T09:30:00-07:00",
                    "source_id": "gmail:account:42:1",
                },
                {
                    "name": "Jon Kim",
                    "amount": "$30.00",
                    "received_at": "2026-08-13T10:00:00-07:00",
                    "source_id": "gmail:account:42:2",
                },
            ],
            self.path,
        )

        self.assertEqual(inserted, 2)
        self.assertEqual(len(payment_history.load(self.path)), 2)

    def test_rebuild_replaces_old_gmail_records(self):
        payment_history.add("Manual", "$5.00", path=self.path, source_id="manual:1")
        payment_history.add("False positive", "$300.00", path=self.path, source_id="gmail:old")

        payment_history.replace_gmail_records(
            [
                {
                    "name": "Maria Lopez",
                    "amount": "$45.00",
                    "source_id": "gmail:account:42:1",
                }
            ],
            self.path,
        )

        records = payment_history.load(self.path)
        self.assertEqual({record["name"] for record in records}, {"Manual", "Maria Lopez"})

    def test_corrupt_history_fails_closed(self):
        Path(self.path).write_text("not json", encoding="utf-8")

        with self.assertRaises(payment_history.HistoryReadError):
            payment_history.add("Maria", "$45.00", path=self.path)

        self.assertEqual(Path(self.path).read_text(encoding="utf-8"), "not json")


if __name__ == "__main__":
    unittest.main()
