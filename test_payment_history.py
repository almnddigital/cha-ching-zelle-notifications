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


if __name__ == "__main__":
    unittest.main()
