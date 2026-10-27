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


class FastHandoffTests(unittest.TestCase):
    def cfg(self, temp):
        return {
            "zip_codes": ["01609", "01760", "02116", "02467", "02026"],
            "period": 180,
            "preferred": "Star White",
            "state_path": Path(temp) / "state.json",
            "ntfy_topic": "",
            "ntfy_server": "https://ntfy.sh",
            "telegram_token": "",
            "telegram_chat_id": "",
            "open_browser": True,
            "browser_app": "Google Chrome",
            "checkout_mode": "chrome_extension",
            "stock_action": "notify",
            "auto_checkout": False,
        }

    def test_new_approved_restock_handoffs_before_remaining_zip_queries_or_slow_alert(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = self.cfg(temp)
            calls = []
            def fetch(zip_code):
                calls.append("fetch:" + zip_code)
                return sample("available")
            def chrome(url, config):
                calls.append("chrome")
                return True
            def notify(*args):
                calls.append("notify")
                return True
            with patch.object(m, "PURCHASE_LOCK", Path(temp) / "not-purchased.json"), \
                 patch.object(m, "fetch_inventory", side_effect=fetch) as network, \
                 patch.object(m, "eligible_pickup_hours", return_value={15: True}), \
                 patch.object(m, "open_from_config", side_effect=chrome), \
                 patch.object(m, "send_alert", side_effect=notify):
                self.assertTrue(m.check(cfg))
                network.assert_called_once_with("01609")
                self.assertEqual(calls, ["fetch:01609", "chrome", "notify"])

    def test_known_stock_does_not_short_circuit_checks_for_new_stores(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.cfg(temp)
            m.write_state(cfg["state_path"], {"status":{"R001|MK1E4LL/A":"in_stock"},
                                               "last_failure_alert":42})
            with patch.object(m, "PURCHASE_LOCK", Path(temp) / "not-purchased.json"), \
                 patch.object(m, "fetch_inventory", return_value=sample("available")) as network, \
                 patch.object(m, "eligible_pickup_hours", return_value={15: True}), \
                 patch.object(m, "send_alert") as alert, \
                 patch.object(m, "open_from_config") as browser:
                self.assertTrue(m.check(cfg))
                self.assertEqual(network.call_count, 5)
                alert.assert_not_called()
                browser.assert_not_called()
                state=m.read_state(cfg["state_path"])
                self.assertEqual(state["last_failure_alert"],42)

    def test_read_only_once_still_checks_every_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.cfg(temp)
            with patch.object(m, "PURCHASE_LOCK", Path(temp) / "not-purchased.json"), \
                 patch.object(m, "fetch_inventory", return_value=sample("available")) as network, \
                 patch.object(m, "send_alert") as alert, \
                 patch.object(m, "open_from_config") as browser:
                self.assertTrue(m.check(cfg,send=False))
                self.assertEqual(network.call_count,5)
                alert.assert_not_called()
                browser.assert_not_called()


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

    def test_chrome_auto_requires_explicit_boolean_auto_checkout(self):
        with patch.dict("os.environ", {"CHECKOUT_MODE": "chrome_auto",
                                        "AUTO_CHECKOUT": "false",
                                        "POLL_SECONDS": "20",
                                        "ZIP_CODES": "01609"}):
            self.assertFalse(m.get_config()["auto_checkout"])
        with patch.dict("os.environ", {"CHECKOUT_MODE": "chrome_auto",
                                        "AUTO_CHECKOUT": "true",
                                        "POLL_SECONDS": "20",
                                        "ZIP_CODES": "01609"}):
            self.assertTrue(m.get_config()["auto_checkout"])

    def test_chrome_auto_invokes_one_shot_extension_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            config = {
                "zip_codes": ["01609"], "period": 20, "preferred": "Star White",
                "state_path": state, "ntfy_topic": "",
                "ntfy_server": "https://ntfy.sh", "telegram_token": "",
                "telegram_chat_id": "", "open_browser": True,
                "browser_app": "Google Chrome", "checkout_mode": "chrome_auto",
                "auto_checkout": True
            }
            with patch.object(m, "PURCHASE_LOCK", Path(tmp) / "missing-lock.json"), \
                 patch.object(m, "fetch_inventory", return_value=sample("available")), \
                 patch.object(m, "send_alert", return_value=False), \
                 patch.object(m, "eligible_pickup_hours", return_value={15: True}), \
                 patch.object(m, "launch_checkout_bot", return_value=True) as buy, \
                 patch.object(m, "open_from_config") as handoff:
                self.assertTrue(m.check(config))
                buy.assert_called_once()
                handoff.assert_not_called()

    def test_launcher_uses_chrome_attempt_in_auto_mode(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            stock = m.Stock("Apple Natick", "R2", "MK1E4LL/A", "Star White", "in_stock", "01609")
            conf = {"checkout_mode": "chrome_auto", "state_path": Path(tmp) / "stock.json"}
            with patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}), \
                 patch.object(m.subprocess, "Popen", return_value=Mock()) as popen:
                self.assertTrue(m.launch_checkout_bot(stock, conf))
                command = popen.call_args.args[0]
                self.assertIn("attempt-chrome", command)
                self.assertNotIn("attempt", command)

    def test_readonly_doctor_never_contacts_apple(self):
        conf = {"period": 180, "checkout_mode": "chrome_extension", "auto_checkout": False}
        with tempfile.TemporaryDirectory() as tmp:
            binpath = Path(tmp) / ".local" / "bin" / "playwright-cli"
            binpath.parent.mkdir(parents=True, exist_ok=True)
            binpath.touch()
            from unittest.mock import Mock
            with patch.object(m, "PURCHASE_LOCK", Path(tmp) / "missing.json"), \
                 patch.object(m.Path, "home", return_value=Path(tmp)), \
                 patch.object(m.sys, "platform", "darwin"), \
                 patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}), \
                 patch.object(m, "fetch_inventory") as fetch, \
                 patch.object(m.subprocess, "run", return_value=Mock(returncode=0)) as cli:
                self.assertTrue(m.doctor(conf))
                fetch.assert_not_called()
                self.assertEqual(cli.call_args.args[0][-1], "tab-list")

    def test_doctor_fails_when_chrome_not_attached(self):
        conf = {"period": 180, "checkout_mode": "chrome_extension", "auto_checkout": False}
        with tempfile.TemporaryDirectory() as tmp:
            binpath = Path(tmp) / ".local" / "bin" / "playwright-cli"
            binpath.parent.mkdir(parents=True, exist_ok=True)
            binpath.touch()
            from unittest.mock import Mock
            with patch.object(m, "PURCHASE_LOCK", Path(tmp) / "missing.json"), \
                 patch.object(m.Path, "home", return_value=Path(tmp)), \
                 patch.object(m.sys, "platform", "darwin"), \
                 patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}), \
                 patch.object(m.subprocess, "run", return_value=Mock(returncode=1)):
                self.assertFalse(m.doctor(conf))

    def test_simulated_stock_follows_only_safe_nonpaying_path(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            conf = {"checkout_mode": "chrome_extension", "stock_action": "dry_run_bag",
                    "auto_checkout": False, "state_path": Path(temp) / "stock.json"}
            with patch.object(m.sys, "platform", "darwin"), \
                 patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}), \
                 patch.object(m, "PURCHASE_LOCK", Path(temp) / "purchase-lock.json"), \
                 patch.object(m, "eligible_pickup_hours", return_value={15: True}), \
                 patch.object(m, "fetch_inventory") as network, \
                 patch.object(m, "launch_checkout_bot") as real_buy, \
                 patch.object(m.subprocess, "Popen", return_value=Mock()) as launch:
                self.assertTrue(m.simulate_stock_trigger(conf, "MK1E4LL/A", "Natick"))
                self.assertFalse(m.simulate_stock_trigger(conf, "MK1E4LL/A", "Natick"))
                real_buy.assert_not_called()
                network.assert_not_called()
                launch.assert_called_once()
                args=launch.call_args.args[0]
                self.assertIn("dry-run-bag", args)
                self.assertNotIn("attempt-chrome", args)
                claim=Path(temp) / "simulated-stock-dry-run-claimed.json"
                self.assertFalse((Path(temp) / "stock-dry-run-claimed.json").exists())
                data=m.json.loads(claim.read_text())
                self.assertEqual(data["mode"], "nonpaying_dry_run")
                self.assertEqual(data["sku"], "MK1E4LL/A")

    def test_simulation_refuses_other_product_and_store(self):
        conf={"stock_action": "dry_run_bag"}
        with patch.object(m, "launch_nonpaying_stock_dry_run") as launch:
            for sku, store in (("OTHER-PRODUCT", "Natick"),
                               ("MK1E4LL/A", "New York Fifth Avenue")):
                with self.assertRaises(ValueError):
                    m.simulate_stock_trigger(conf, sku, store)
            launch.assert_not_called()

    def test_safe_stock_action_requires_explicit_optin(self):
        with patch.dict("os.environ", {"CHECKOUT_MODE": "chrome_extension",
                                        "STOCK_ACTION": "dry_run_bag",
                                        "AUTO_CHECKOUT": "true",
                                        "POLL_SECONDS": "180",
                                        "ZIP_CODES": "01609"}):
            config=m.get_config()
            self.assertEqual(config["stock_action"], "dry_run_bag")
            self.assertFalse(config["auto_checkout"])
        with patch.dict("os.environ", {"STOCK_ACTION": "unknown", "ZIP_CODES": "01609"}):
            with self.assertRaises(ValueError):
                m.get_config()

    def test_real_qualifying_stock_starts_nonpaying_dryrun(self):
        conf = {"zip_codes": ["01609"], "period": 180, "preferred": "Star White",
                "state_path": Path("/tmp/duo-stock-demo/state.json"),
                "ntfy_topic": "", "ntfy_server": "https://ntfy.sh",
                "telegram_token": "", "telegram_chat_id": "",
                "open_browser": True, "browser_app": "Google Chrome",
                "checkout_mode": "chrome_extension", "stock_action": "dry_run_bag",
                "auto_checkout": False}
        with tempfile.TemporaryDirectory() as temp:
            conf["state_path"] = Path(temp) / "state.json"
            with patch.object(m, "PURCHASE_LOCK", Path(temp) / "purchase-lock.json"), \
                 patch.object(m, "fetch_inventory", return_value=sample("available")), \
                 patch.object(m, "eligible_pickup_hours", return_value={15: True}), \
                 patch.object(m, "send_alert", return_value=False), \
                 patch.object(m, "open_from_config") as handoff, \
                 patch.object(m, "launch_checkout_bot") as live_buy, \
                 patch.object(m, "launch_nonpaying_stock_dry_run", return_value=True) as test_buy:
                self.assertTrue(m.check(conf))
                test_buy.assert_called_once()
                live_buy.assert_not_called()
                handoff.assert_not_called()

    def test_nonpaying_dryrun_rejected_outside_mac_or_purchase_locked(self):
        with tempfile.TemporaryDirectory() as temp:
            conf={"checkout_mode":"chrome_extension", "auto_checkout":False,
                  "state_path":Path(temp)/"stock.json"}
            item=m.Stock("Natick","R001","MK1E4LL/A","White 256GB","in_stock","01609")
            with patch.object(m.sys, "platform", "linux"), \
                 patch.object(m.subprocess, "Popen") as launch:
                self.assertFalse(m.launch_nonpaying_stock_dry_run(item,conf))
                launch.assert_not_called()

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
