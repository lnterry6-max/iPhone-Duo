import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
import checkout_bot as bot
from checkout_bot import CheckoutError, summary_ok, validate_auth


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
