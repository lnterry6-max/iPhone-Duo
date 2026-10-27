import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
import checkout_bot as bot
from checkout_bot import CheckoutError, summary_ok, validate_auth


class PaymentPreflightTests(unittest.TestCase):
    def test_preflight_never_purchases_or_queries_private_apple_stock(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(bot, "AUTH", Path(tmp) / "missing-auth.json"), \
             patch.object(bot, "PURCHASE_LOCK", Path(tmp) / "missing-lock.json"), \
             patch.object(bot, "get_config", return_value={
                 "checkout_mode": "chrome_extension",
                 "stock_action": "dry_run_bag",
                 "auto_checkout": False
             }), \
             patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch.object(bot, "fetch_inventory") as fetch, \
             patch.object(bot, "chrome_checkout_flow") as flow, \
             patch.object(bot, "attempt_chrome") as pay, \
             patch("builtins.print") as output:
            self.assertFalse(bot.payment_preflight())
            fetch.assert_not_called()
            flow.assert_not_called()
            pay.assert_not_called()
            labels = [str(c.args[0]) for c in output.call_args_list]
            self.assertTrue(any("NOT READY" in line for line in labels))
            self.assertTrue(any("Fresh verified Apple stock" in line for line in labels))
            self.assertTrue(any("Exact store/date/time final review" in line for line in labels))


class SinglePurchaseLockTests(unittest.TestCase):
    def test_apple_prefix_store_verified_and_one_submit_prevents_second_attempt(self):
        from duo_monitor import Stock
        item = Stock("Apple Natick", "R001", "MK1E4LL/A",
                     "Star White — 256GB", "in_stock", "01609")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            auth = {"status":"armed", "expires_at": bot.time.time() + 3600,
                    "max_total_usd":2200, "quantity":1,
                    "allow_submit":True, "checkout_mode":"chrome_auto"}
            args = Mock(sku="MK1E4LL/A", store_id="R001",
                        store_name="Natick", zip_code="01609")
            with patch.object(bot, "AUTH", base / "auth.json"), \
                 patch.object(bot, "PURCHASE_LOCK", base / "purchase-lock.json"), \
                 patch.object(bot, "LOCK", base / "attempt.lock"), \
                 patch.object(bot, "read_auth", return_value=auth), \
                 patch.object(bot, "get_config", return_value={"checkout_mode":"chrome_auto"}), \
                 patch.object(bot, "verify_stock", return_value=item) as verify, \
                 patch.object(bot, "eligible_pickup_hours", return_value={15:True}), \
                 patch.object(bot, "connected_chrome_ready", return_value=True), \
                 patch.object(bot, "chrome_checkout_flow",
                              return_value={"status":"submitted_unverified"}) as flow, \
                 patch.object(bot, "notify_checkout"):
                bot.attempt_chrome(args)
                self.assertEqual(flow.call_count,1)
                result=bot.json.loads((base / "purchase-lock.json").read_text())
                self.assertEqual(result["status"],"submitted_unverified")
                self.assertEqual(auth["status"],"attempted")
                # Even a fresh authorization must not permit a second attempt.
                auth["status"]="armed"
                with self.assertRaises(CheckoutError):
                    bot.attempt_chrome(args)
                flow.assert_called_once()
                verify.assert_called_once()

    def test_unknown_browser_failure_keeps_global_purchase_lock(self):
        from duo_monitor import Stock
        item = Stock("Apple Natick", "R001", "MK1E4LL/A",
                     "Star White — 256GB", "in_stock", "01609")
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            auth={"status":"armed", "expires_at":bot.time.time()+3600,
                  "max_total_usd":2200, "quantity":1,
                  "allow_submit":True, "checkout_mode":"chrome_auto"}
            args=Mock(sku="MK1E4LL/A",store_id="R001",
                      store_name="Natick",zip_code="01609")
            with patch.object(bot,"AUTH",base/"auth.json"), \
                 patch.object(bot,"PURCHASE_LOCK",base/"purchase-lock.json"), \
                 patch.object(bot,"LOCK",base/"attempt.lock"), \
                 patch.object(bot,"read_auth",return_value=auth), \
                 patch.object(bot,"get_config",return_value={"checkout_mode":"chrome_auto"}), \
                 patch.object(bot,"verify_stock",return_value=item), \
                 patch.object(bot,"eligible_pickup_hours",return_value={15:True}), \
                 patch.object(bot,"connected_chrome_ready",return_value=True), \
                 patch.object(bot,"chrome_checkout_flow",side_effect=RuntimeError("unknown Apple response")) as flow, \
                 patch.object(bot,"notify_checkout"):
                with self.assertRaises(RuntimeError):
                    bot.attempt_chrome(args)
                lock=bot.json.loads((base/"purchase-lock.json").read_text())
                self.assertEqual(lock["status"],"checkout_started")
                auth["status"]="armed"
                with self.assertRaises(CheckoutError):
                    bot.attempt_chrome(args)
                flow.assert_called_once()


class AuthorizationTests(unittest.TestCase):
    def test_only_256gb(self):
        with self.assertRaises(CheckoutError):
            validate_auth({'status':'armed','expires_at':2000,'max_total_usd':2200,'quantity':1,'allow_submit':True}, 'OTHER', now=1000)

    def test_prevents_second_attempt(self):
        with self.assertRaises(CheckoutError):
            validate_auth({'status':'attempted','expires_at':2000,'max_total_usd':2200,'quantity':1,'allow_submit':True}, 'MK1E4LL/A', now=1000)

    def test_requires_explicit_consent(self):
        with self.assertRaises(CheckoutError):
            validate_auth({'status':'armed','expires_at':2000,'max_total_usd':2200,'quantity':1,'allow_submit':False}, 'MK1E4LL/A', now=1000)

    def test_refuses_expired(self):
        with self.assertRaises(CheckoutError):
            validate_auth({'status':'armed','expires_at':1000,'max_total_usd':2200,'quantity':1,'allow_submit':True}, 'MK1E4LL/A', now=2000)

    
class LoginSafetyTests(unittest.TestCase):
    def test_browser_default_is_installed_chrome(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(bot.checkout_browser(), "chrome")
            self.assertTrue(str(bot.browser_profile()).endswith("apple-browser-chrome"))

    def test_testing_browser_uses_distinct_local_profile(self):
        with patch.dict("os.environ", {"CHECKOUT_BROWSER": "chromium"}):
            self.assertTrue(str(bot.browser_profile()).endswith("apple-browser-chromium"))

    def test_invalid_browser_refused(self):
        with patch.dict("os.environ", {"CHECKOUT_BROWSER": "safari"}):
            with self.assertRaises(CheckoutError):
                bot.checkout_browser()

    def test_spinning_login_cannot_enable_checkout(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bot, "LOGIN_CONFIRMATION", Path(tmp) / "no-confirmed-login.json"):
            with self.assertRaises(CheckoutError):
                bot.require_verified_login()



class ChromeAutomationTests(unittest.TestCase):
    def test_mode_requires_separate_opt_in(self):
        with patch.object(bot, "get_config", return_value={"checkout_mode": "browser_handoff"}), \
             patch.object(bot, "require_verified_login") as login:
            with self.assertRaises(CheckoutError):
                bot.arm(Mock(max_total=2200, hours=4))
            login.assert_not_called()

    def test_chrome_autopurchase_arming_requires_attached_browser(self):
        with patch.object(bot, "get_config", return_value={"checkout_mode": "chrome_auto"}), \
             patch.object(bot, "connected_chrome_ready", return_value=False):
            with self.assertRaises(CheckoutError):
                bot.arm(Mock(max_total=2200, hours=4))

    def test_chrome_mode_arm_stores_its_mode_and_limit(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(bot, "AUTH", Path(tmp) / "authorization.json"), \
             patch.object(bot, "PURCHASE_LOCK", Path(tmp) / "missing-lock.json"), \
             patch.object(bot, "get_config", return_value={"checkout_mode": "chrome_auto"}), \
             patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch("builtins.input", return_value="BUY ONE DUO"):
            bot.arm(Mock(max_total=2200, hours=4))
            saved = bot.json.loads((Path(tmp) / "authorization.json").read_text())
            self.assertEqual(saved["checkout_mode"], "chrome_auto")
            self.assertEqual(saved["quantity"], 1)
            self.assertEqual(saved["max_total_usd"], 2200)

    def test_chrome_checkout_flow_dry_run_does_not_request_submission(self):
        from duo_monitor import Stock
        stock = Stock("Apple Natick", "R002", "MK1E4LL/A", "Star White - 256GB", "in_stock", "01609")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(bot, "PROFILE_ROOT", Path(tmp)), \
             patch.object(bot, "chrome_cli", return_value=Path(tmp) / "playwright-cli"), \
             patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch.object(bot.subprocess, "run", side_effect=[
                 Mock(returncode=0),
                 Mock(returncode=0, stdout='DUO_AUTOMATION_RESULT={"status":"review_verified","total_usd":2125.45}')
             ]) as run:
            output = bot.chrome_checkout_flow(stock, 2200, [15, 16], submit_order=False)
            self.assertEqual(output["status"], "review_verified")
            cmd = run.call_args_list[1].args[0]
            self.assertEqual(cmd[:4], [str(Path(tmp) / "playwright-cli"), "-s=chrome", "--raw", "run-code"])
            self.assertFalse(list(Path(tmp).glob("chrome-flow-*.js")))

    def test_bag_resume_uses_existing_bag_and_never_submits_payment(self):
        from duo_monitor import Stock
        stock = Stock("Apple Natick", "R002", "MK1E4LL/A",
                      "Star White - 256GB", "unknown", "01609")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(bot, "PROFILE_ROOT", Path(tmp)), \
             patch.object(bot, "chrome_cli", return_value=Path(tmp) / "playwright-cli"), \
             patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch.object(bot.subprocess, "run", side_effect=[
                 Mock(returncode=0),
                 Mock(returncode=0, stdout='DUO_AUTOMATION_RESULT={"status":"stopped","stage":"pickup","code":"pickup_store_missing"}')
             ]) as run:
            result = bot.chrome_checkout_flow(stock, 2200, [15, 16],
                                              submit_order=False, resume_bag=True)
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(run.call_args_list[0].args[0][-1], "https://www.apple.com/shop/bag")
            self.assertFalse(list(Path(tmp).glob("chrome-flow-*.js")))

    def test_resumed_bag_cannot_submit_real_purchase(self):
        from duo_monitor import Stock
        stock = Stock("Apple Natick", "R002", "MK1E4LL/A", "Star White - 256GB",
                      "unknown", "01609")
        with patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch.object(bot.subprocess, "run") as run:
            with self.assertRaises(CheckoutError):
                bot.chrome_checkout_flow(stock, 2200, [15], submit_order=True,
                                         resume_bag=True)
            run.assert_not_called()

    def test_unexpected_cli_output_fails_closed(self):
        from duo_monitor import Stock
        stock = Stock("Apple Natick", "R002", "MK1E4LL/A", "Star White - 256GB", "in_stock", "01609")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(bot, "PROFILE_ROOT", Path(tmp)), \
             patch.object(bot, "chrome_cli", return_value=Path(tmp) / "playwright-cli"), \
             patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch.object(bot.subprocess, "run", side_effect=[
                 Mock(returncode=0), Mock(returncode=0, stdout="unexpected output")
             ]):
            with self.assertRaises(CheckoutError):
                bot.chrome_checkout_flow(stock, 2200, [15], submit_order=True)


    def test_raw_and_json_quoted_chrome_results(self):
        expected = {"status": "stopped", "stage": "applecare",
                    "code": "no_applecare_option_missing", "clickedOrderButton": False}
        value = "DUO_AUTOMATION_RESULT=" + bot.json.dumps(expected)
        self.assertEqual(bot.parse_chrome_cli_result(value), expected)
        self.assertEqual(bot.parse_chrome_cli_result(bot.json.dumps(value)), expected)

    def test_raw_chrome_result_with_nested_object(self):
        value = 'DUO_AUTOMATION_RESULT={"status":"stopped","stage":"product","code":"missing","debug":{"attempted":false}}'
        parsed = bot.parse_chrome_cli_result(value)
        self.assertEqual(parsed["stage"], "product")
        self.assertNotIn("debug", parsed)

    def test_chrome_parser_rejects_unverified_messages(self):
        with self.assertRaises(CheckoutError):
            bot.parse_chrome_cli_result("User account information from website")
        with self.assertRaises(CheckoutError):
            bot.parse_chrome_cli_result("DUO_AUTOMATION_RESULT={invalid")

    def test_no_applecare_option_is_explicit_in_script(self):
        script = Path(__file__).resolve().parents[1] / "chrome_checkout_flow.js"
        source = script.read_text(encoding="utf-8")
        self.assertIn("chooseNoAppleCare()", source)
        self.assertIn("no_applecare_option_missing", source)
        self.assertIn("unexpected_applecare", source)
        self.assertIn("if (cfg.submit_order === false)", source)



class TestProductInspectorTests(unittest.TestCase):
    def test_inspector_readonly_on_selected_tab(self):
        data = 'DUO_TEST_PICKUP_INSPECT={"status":"read_only","controls":["button: Check availability","link: Pickup"],"stores":["Natick"]}'
        with patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch.object(bot.subprocess, "run", return_value=Mock(returncode=0, stdout=data)) as run, \
             patch.object(bot, "attempt_chrome") as buying:
            bot.inspect_test_product()
            buying.assert_not_called()
            args = run.call_args.args[0]
            self.assertEqual(args[1:4], ["-s=chrome","--raw","run-code"])
            self.assertTrue(args[4].endswith("inspect_test_product.js"))

    def test_pickup_signal_is_labeled_unconfirmed_and_limited_to_test_product(self):
        from unittest.mock import call
        result = ('DUO_TEST_PICKUP_INSPECT=' +
                  bot.json.dumps({
                    "status": "read_only",
                    "controls": ["button: Check availability"],
                    "stores": ["The Shops at Blackstone Valley"],
                    "storeAvailability": [{
                        "store": "The Shops at Blackstone Valley",
                        "availability": "available"
                    }],
                    "pickupUiPresent": True,
                  }))
        with patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch.object(bot.subprocess, "run",
                          return_value=Mock(returncode=0, stdout=result)), \
             patch("builtins.print") as printing:
            bot.inspect_test_product()
        lines = [str(c.args[0]) for c in printing.call_args_list]
        self.assertTrue(any("unconfirmed UI signal" in x for x in lines))
        self.assertTrue(any("test product only" in x for x in lines))

    def test_inspector_refuses_unapproved_store_result(self):
        result = ('DUO_TEST_PICKUP_INSPECT=' +
                  bot.json.dumps({"status":"read_only","controls":[],
                                  "stores":["Apple Fifth Avenue"],
                                  "storeAvailability":[],
                                  "pickupUiPresent":False}))
        with patch.object(bot,"connected_chrome_ready",return_value=True), \
             patch.object(bot.subprocess,"run",
                          return_value=Mock(returncode=0,stdout=result)):
            with self.assertRaises(CheckoutError):
                bot.inspect_test_product()

    def test_inspector_rejects_untrusted_or_malformed_result(self):
        with patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch.object(bot.subprocess, "run", return_value=Mock(returncode=0, stdout="secret account output")):
            with self.assertRaises(CheckoutError):
                bot.inspect_test_product()

class AppleCareInspectionTests(unittest.TestCase):
    def test_readonly_diagnostic_parses_only_relevant_controls(self):
        output = 'DUO_CARE_INSPECT=' + bot.json.dumps({
            "status": "controls_found",
            "controls": [
                {"role": "radio", "label": "No AppleCare+ coverage", "disabled": False},
                {"role": "button", "label": "AppleCare+ coverage", "disabled": False},
                {"role": "link", "label": "Account information", "disabled": False}
            ]
        })
        parsed = bot.parse_care_inspection(output)
        self.assertEqual(parsed["status"], "controls_found")
        self.assertEqual([p["label"] for p in parsed["controls"]],
                         ["No AppleCare+ coverage", "AppleCare+ coverage"])

    def test_chrome_quoted_diagnostic(self):
        output = bot.json.dumps('DUO_CARE_INSPECT={"status":"no_visible_care_controls","controls":[]}')
        self.assertEqual(bot.parse_care_inspection(output)["controls"], [])

    def test_diagnostic_rejects_raw_account_data(self):
        with self.assertRaises(CheckoutError):
            bot.parse_care_inspection("Apple account logged in")
        with self.assertRaises(CheckoutError):
            bot.parse_care_inspection('DUO_CARE_INSPECT={"status":"unknown","controls":[]}')

    def test_inspector_runs_with_read_only_script(self):
        from unittest.mock import Mock
        with patch.object(bot, "connected_chrome_ready", return_value=True), \
             patch.object(bot.subprocess, "run", return_value=Mock(
                 returncode=0,
                 stdout='DUO_CARE_INSPECT={"status":"no_visible_care_controls","controls":[]}'
             )) as run:
            bot.inspect_applecare()
            command = run.call_args.args[0]
            self.assertEqual(command[1:4], ["-s=chrome", "--raw", "run-code"])
            self.assertTrue(command[4].startswith("--filename="))
            self.assertIn("inspect_applecare.js", command[4])


class SummaryTests(unittest.TestCase):
    def test_exact_model_color_and_pickup(self):
        summary = 'Order Summary | iPhone Duo 256GB Star White | Qty: 1 | Pick up at Apple Natick Tuesday, October 27, 2026 at 3:00 PM | Order Total: $2,125.45'
        self.assertAlmostEqual(summary_ok(summary, 'MK1E4LL/A', 'Natick', 2200), 2125.45)

    def test_refuse_wrong_color(self):
        with self.assertRaises(CheckoutError):
            summary_ok('iPhone Duo 256GB Night Sky Qty: 1 Pick up Natick Tuesday, October 27, 2026 at 3:00 PM Total $2100.00', 'MK1E4LL/A','Natick',2200)

    def test_refuse_over_cap(self):
        with self.assertRaises(CheckoutError):
            summary_ok('iPhone Duo 256GB Star White Qty: 1 Pick up Natick Tuesday, October 27, 2026 at 3:00 PM Total $2300.00', 'MK1E4LL/A','Natick',2200)

    def test_refuse_no_qty(self):
        with self.assertRaises(CheckoutError):
            summary_ok('iPhone Duo 256GB Star White Pick up Natick Tuesday, October 27, 2026 at 3:00 PM Total $2100.00', 'MK1E4LL/A','Natick',2200)

    def test_refuse_other_capacity(self):
        with self.assertRaises(CheckoutError):
            summary_ok('iPhone Duo 256GB Star White 512GB Qty 1 Pick up Natick Tuesday, October 27, 2026 at 3:00 PM Total $2100.00', 'MK1E4LL/A','Natick',2200)

if __name__ == '__main__':
    unittest.main()
