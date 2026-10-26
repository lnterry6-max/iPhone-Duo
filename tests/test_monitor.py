import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duo_monitor as m


def sample(white="unavailable", black="unavailable"):
    return {"body": {"stores": [
        {"storeNumber": "R001", "storeName": "Apple Natick", "partsAvailability": {
            "MK1E4LL/A": {"pickupDisplay": white},
            "MK1F4LL/A": {"pickupDisplay": black},
        }},
        {"storeNumber": "R002", "storeName": "Apple Legacy Place", "partsAvailability": {
            "MK1E4LL/A": {"pickupDisplay": "unavailable"},
            "MK1F4LL/A": {"pickupDisplay": "unavailable"},
        }},
    ]}}


class ProductTests(unittest.TestCase):
    def test_only_256gb_skus(self):
        self.assertEqual(set(m.PRODUCTS), {"MK1E4LL/A", "MK1F4LL/A"})
        self.assertIn("parts.0=MK1E4LL%2FA", m.stock_url("01609"))
        self.assertIn("parts.1=MK1F4LL%2FA", m.stock_url("01609"))

    def test_ignores_all_other_apple_stores(self):
        payload = sample("unavailable", "unavailable")
        payload["body"]["stores"].append({
            "storeNumber": "R999", "storeName": "Apple South Shore",
            "partsAvailability": {
                "MK1E4LL/A": {"pickupDisplay": "available"},
                "MK1F4LL/A": {"pickupDisplay": "available"},
            },
        })
        parsed = m.parse_inventory(payload, "01609")
        self.assertNotIn("R999", {item.store_id for item in parsed})
        self.assertEqual(len(parsed), 4)

    def test_zip_with_no_allowed_stores_is_not_an_error(self):
        payload = {"body": {"stores": [{
            "storeNumber": "R999", "storeName": "Apple South Shore",
            "partsAvailability": {"MK1E4LL/A": {"pickupDisplay": "available"}},
        }]}}
        self.assertEqual(m.parse_inventory(payload, "01609"), [])

    def test_unavailable_not_falsely_reported_available(self):
        items = m.parse_inventory(sample("unavailable", "available"), "01609")
        self.assertEqual([s.sku for s in items if s.status == "in_stock"], ["MK1F4LL/A"])

    def test_missing_sku_is_not_sold_out(self):
        with self.assertRaises(m.InventoryError):
            m.parse_inventory({"body": {"stores": [{"storeNumber": "R1", "storeName": "Apple Natick", "partsAvailability": {}}]}}, "01609")

    def test_unknown_status_preserves_state(self):
        items = m.parse_inventory(sample("??", "unavailable"), "01609")
        new, status = m.compute_new_stock(items, {"R001|MK1E4LL/A": "in_stock"})
        self.assertEqual(new, [])
        self.assertEqual(status["R001|MK1E4LL/A"], "in_stock")

    def test_new_stock_then_dedup_then_restock(self):
        initial = m.parse_inventory(sample("available"), "01609")
        new, state = m.compute_new_stock(initial, {})
        self.assertEqual(len(new), 1)
        new, state = m.compute_new_stock(initial, state)
        self.assertEqual(len(new), 0)
        new, state = m.compute_new_stock(m.parse_inventory(sample(), "01609"), state)
        self.assertEqual(len(new), 0)
        new, state = m.compute_new_stock(initial, state)
        self.assertEqual(len(new), 1)

    def test_state_persistence_after_alert(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            config = {"zip_codes": ["01609"], "period": 20, "preferred": "Star White", "state_path": path,
                      "ntfy_topic": "", "ntfy_server": "https://ntfy.sh", "telegram_token": "",
                      "telegram_chat_id": "", "open_browser": False}
            with patch.object(m, "fetch_inventory", return_value=sample("available")), patch.object(m, "send_alert", return_value=True) as notifier, patch.object(m, "eligible_pickup_hours", return_value={15: True}):
                self.assertTrue(m.check(config, send=True))
                self.assertTrue(m.check(config, send=True))
                self.assertEqual(notifier.call_count, 1)
            self.assertEqual(m.read_state(path)["status"]["R001|MK1E4LL/A"], "in_stock")

    def test_read_only_check_does_not_consume_alert(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            config = {"zip_codes": ["01609"], "period": 20, "preferred": "Star White", "state_path": path,
                      "ntfy_topic": "", "ntfy_server": "https://ntfy.sh", "telegram_token": "",
                      "telegram_chat_id": "", "open_browser": False}
            with patch.object(m, "fetch_inventory", return_value=sample("available")):
                self.assertTrue(m.check(config, send=False))
            self.assertFalse(path.exists())

    def test_bad_response_does_not_erase_state(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            m.write_state(path, {"status": {"R001|MK1E4LL/A": "in_stock"}})
            config = {"zip_codes": ["01609"], "period": 20, "preferred": "Star White", "state_path": path,
                      "ntfy_topic": "", "ntfy_server": "https://ntfy.sh", "telegram_token": "",
                      "telegram_chat_id": "", "open_browser": False}
            with patch.object(m, "fetch_inventory", side_effect=m.InventoryError("blocked")):
                self.assertFalse(m.check(config))
            self.assertEqual(m.read_state(path)["status"]["R001|MK1E4LL/A"], "in_stock")


if __name__ == "__main__":
    unittest.main()
