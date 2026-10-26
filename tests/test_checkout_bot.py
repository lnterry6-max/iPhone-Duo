import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
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
