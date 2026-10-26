import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import duo_monitor
import pickup_rules as p


class PickupRulesTests(unittest.TestCase):
    def test_exact_five_store_allowlist(self):
        names = (
            "Apple The Shops at Blackstone Valley", "Apple Natick",
            "Apple Boylston Street", "Apple Chestnut Hill", "Apple Legacy Place",
        )
        self.assertEqual({p.canonical_store(s) for s in names}, set(p.STORE_ADDRESSES))
        self.assertIsNone(p.canonical_store("Apple South Shore"))
        self.assertIsNone(p.canonical_store("Random Legacy Place West"))

    def test_pickup_requires_exact_date_and_hour(self):
        self.assertEqual(p.assert_pickup_slot("Pick up at Natick: Tue, Oct 27, 2026 at 3:00 PM"), 15)
        self.assertEqual(p.assert_pickup_slot("Pickup at Legacy Place: 10/27/2026 4:00 p.m."), 16)
        for summary in (
            "Pick up Oct 28, 2026 at 3:00 PM",
            "Pick up Oct 27, 2026 at 3:30 PM",
            "Deliver Oct 27, 2026 at 3:00 PM",
        ):
            with self.subTest(summary=summary), self.assertRaises(p.PickupConstraintError):
                p.assert_pickup_slot(summary)

    def test_routes_reject_more_than_55_minutes_with_buffer(self):
        now = datetime(2026, 10, 26, 19, 0, tzinfo=p.BOSTON)
        with patch.object(p, "route_duration_minutes", side_effect=[54, 58]):
            self.assertEqual(p.eligible_pickup_hours("Apple Boylston Street", now=now), {15: 54})
        with patch.object(p, "route_duration_minutes", return_value=60):
            with self.assertRaises(p.PickupConstraintError):
                p.eligible_pickup_hours("Legacy Place", now=now)

    def test_no_routes_api_key_fails_closed(self):
        now = datetime(2026, 10, 26, 19, 0, tzinfo=p.BOSTON)
        with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}):
            with self.assertRaises(p.PickupConstraintError):
                p.eligible_pickup_hours("Natick", now=now)

    def test_expired_window_fails_closed(self):
        with self.assertRaises(p.PickupConstraintError):
            p.eligible_pickup_hours("Natick", now=datetime(2026, 10, 28, 12, tzinfo=p.BOSTON))


class PurchaseLockTests(unittest.TestCase):
    def test_purchase_lock_halts_monitor_before_any_api_call(self):
        with tempfile.TemporaryDirectory() as temp:
            latch = Path(temp) / "purchase-lock.json"
            latch.write_text(json.dumps({"status": "submitted_unverified"}))
            with patch.object(duo_monitor, "PURCHASE_LOCK", latch), patch.object(duo_monitor, "fetch_inventory") as fetch:
                self.assertIn("stopped", duo_monitor.purchase_lock_reason())
                self.assertTrue(duo_monitor.check({"zip_codes": ["01609"]}))
                fetch.assert_not_called()

    def test_invalid_lock_also_halts_monitor(self):
        with tempfile.TemporaryDirectory() as temp:
            latch = Path(temp) / "purchase-lock.json"
            latch.write_text("corrupted")
            with patch.object(duo_monitor, "PURCHASE_LOCK", latch):
                self.assertIn("unreadable", duo_monitor.purchase_lock_reason())


if __name__ == "__main__":
    unittest.main()
