import unittest
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


class SummaryTests(unittest.TestCase):
    def test_exact_model_color_and_pickup(self):
        summary = 'Order Summary | iPhone Duo 256GB Star White | Qty: 1 | Pick up at Apple Natick | Order Total: $2,125.45'
        self.assertAlmostEqual(summary_ok(summary, 'MK1E4LL/A', 'Natick', 2200), 2125.45)

    def test_refuse_wrong_color(self):
        with self.assertRaises(CheckoutError):
            summary_ok('iPhone Duo 256GB Night Sky Qty: 1 Pick up Natick Total $2100.00', 'MK1E4LL/A','Natick',2200)

    def test_refuse_over_cap(self):
        with self.assertRaises(CheckoutError):
            summary_ok('iPhone Duo 256GB Star White Qty: 1 Pick up Natick Total $2300.00', 'MK1E4LL/A','Natick',2200)

    def test_refuse_no_qty(self):
        with self.assertRaises(CheckoutError):
            summary_ok('iPhone Duo 256GB Star White Pick up Natick Total $2100.00', 'MK1E4LL/A','Natick',2200)

    def test_refuse_other_capacity(self):
        with self.assertRaises(CheckoutError):
            summary_ok('iPhone Duo 256GB Star White 512GB Qty 1 Pick up Natick Total $2100.00', 'MK1E4LL/A','Natick',2200)

if __name__ == '__main__':
    unittest.main()
