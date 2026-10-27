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
    def test_default_handoff_blocks_experimental_checkout_even_if_env_says_true(self):
        with patch.dict("os.environ", {"AUTO_CHECKOUT": "true", "CHECKOUT_MODE": "browser_handoff",
                                        "BROWSER_APP": "Safari", "POLL_SECONDS": "20",
                                        "ZIP_CODES": "01609"}):
            config = m.get_config()
            self.assertFalse(config["auto_checkout"])
            self.assertEqual(config["browser_app"], "Safari")

    def test_handoff_to_personal_safari_uses_open_a_and_no_checkout(self):
        with patch.object(m.sys, "platform", "darwin"), patch.object(m.subprocess, "Popen") as popen:
            self.assertTrue(m.open_checkout_page(m.BUY_URLS["MK1F4LL/A"], "Safari"))
            self.assertEqual(popen.call_args.args[0][:3], ["open", "-a", "Safari"])

    def test_handoff_to_personal_chrome(self):
        with patch.object(m.sys, "platform", "darwin"), patch.object(m.subprocess, "Popen") as popen:
            self.assertTrue(m.open_checkout_page(m.BUY_URLS["MK1E4LL/A"], "Google Chrome"))
            self.assertEqual(popen.call_args.args[0][:3], ["open", "-a", "Google Chrome"])

    def test_never_handoff_to_non_apple_url(self):
        with patch.object(m.subprocess, "Popen") as popen:
            self.assertFalse(m.open_checkout_page("https://example.com/checkout"))
            popen.assert_not_called()

    def test_manual_handoff_does_not_launch_checkout_automation(self):
        with tempfile.TemporaryDirectory() as temp:
            config = {"zip_codes": ["01609"], "period": 20, "preferred": "Star White",
                      "state_path": Path(temp) / "stock.json", "ntfy_topic": "",
                      "ntfy_server": "https://ntfy.sh", "telegram_token": "",
                      "telegram_chat_id": "", "open_browser": True,
                      "browser_app": "Safari", "checkout_mode": "browser_handoff",
                      "auto_checkout": True}
            with patch.object(m, "PURCHASE_LOCK", Path(temp) / "no-purchase-lock.json"), \
                 patch.object(m, "fetch_inventory", return_value=sample("available")), \
                 patch.object(m, "send_alert", return_value=False), \
                 patch.object(m, "eligible_pickup_hours", return_value={15: True}), \
                 patch.object(m, "launch_checkout_bot") as checkout, \
                 patch.object(m, "open_checkout_page", return_value=True) as handoff:
                self.assertTrue(m.check(config))
                checkout.assert_not_called()
                handoff.assert_called_once()

    def test_chrome_extension_mode_never_enables_auto_checkout(self):
        with patch.dict("os.environ", {"CHECKOUT_MODE": "chrome_extension", "AUTO_CHECKOUT": "true",
                                        "ZIP_CODES": "01609", "POLL_SECONDS": "20"}):
            config = m.get_config()
            self.assertEqual(config["checkout_mode"], "chrome_extension")
            self.assertFalse(config["auto_checkout"])

    def test_connected_chrome_opens_approved_url_in_existing_session(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "playwright-cli"
            binary.touch()
            with patch.object(m.sys, "platform", "darwin"), \
                 patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}), \
                 patch.object(m.subprocess, "run", return_value=Mock(returncode=0)) as run:
                url = m.BUY_URLS["MK1F4LL/A"]
                self.assertTrue(m.open_in_connected_chrome(url, cli_path=binary))
                self.assertEqual(run.call_args.args[0], [str(binary), "-s=chrome", "tab-new", url])

    def test_github_hosted_runner_cannot_control_connected_chrome(self):
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), \
             patch.object(m.subprocess, "run") as run:
            self.assertFalse(m.open_in_connected_chrome(m.BUY_URLS["MK1E4LL/A"]))
            run.assert_not_called()

    def test_connected_chrome_rejects_unapproved_url_without_launching(self):
        with patch.object(m.subprocess, "run") as run:
            self.assertFalse(m.open_in_connected_chrome("https://example.com/checkout"))
            self.assertFalse(m.open_in_connected_chrome("https://www.apple.com/shop/bag"))
            run.assert_not_called()

    def test_extension_unavailable_falls_back_to_normal_chrome(self):
        with patch.object(m, "open_in_connected_chrome", return_value=False), \
             patch.object(m, "open_checkout_page", return_value=True) as fallback:
            self.assertTrue(m.open_from_config(m.BUY_URLS["MK1E4LL/A"],
                                              {"checkout_mode": "chrome_extension", "browser_app": "Safari"}))
            fallback.assert_called_once_with(m.BUY_URLS["MK1E4LL/A"], "Google Chrome")

    def test_chrome_extension_handoff_never_launches_checkout_bot(self):
        with tempfile.TemporaryDirectory() as temp:
            config = {"zip_codes": ["01609"], "period": 20, "preferred": "Star White",
                      "state_path": Path(temp) / "stock.json", "ntfy_topic": "",
                      "ntfy_server": "https://ntfy.sh", "telegram_token": "",
                      "telegram_chat_id": "", "open_browser": True,
                      "browser_app": "Google Chrome", "checkout_mode": "chrome_extension",
                      "auto_checkout": True}
            with patch.object(m, "PURCHASE_LOCK", Path(temp) / "no-lock.json"), \
                 patch.object(m, "fetch_inventory", return_value=sample("available")), \
                 patch.object(m, "send_alert", return_value=False), \
                 patch.object(m, "eligible_pickup_hours", return_value={15: True}), \
                 patch.object(m, "launch_checkout_bot") as buy, \
                 patch.object(m, "open_from_config", return_value=True) as handoff:
                self.assertTrue(m.check(config))
                buy.assert_not_called()
                handoff.assert_called_once_with(m.BUY_URLS["MK1E4LL/A"], config)

    def test_confirmed_purchase_stops_watcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "purchase-lock.json"
            with patch.object(m, "PURCHASE_LOCK", lock), \
                 patch("builtins.input", return_value="ORDER CONFIRMED"), \
                 patch.object(m, "fetch_inventory") as fetch:
                m.mark_purchased()
                self.assertTrue(lock.exists())
                self.assertEqual(m.json.loads(lock.read_text())["status"], "manually_confirmed")
                self.assertTrue(m.check({"zip_codes": ["01609"]}))
                fetch.assert_not_called()

    def test_mark_purchased_requires_real_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "purchase-lock.json"
            with patch.object(m, "PURCHASE_LOCK", lock), \
                 patch("builtins.input", return_value="no"):
                with self.assertRaises(ValueError):
                    m.mark_purchased()
                self.assertFalse(lock.exists())

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
