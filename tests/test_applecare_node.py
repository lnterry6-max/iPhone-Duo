import shutil
import subprocess
import unittest
from pathlib import Path


class AppleCareJavaScriptTests(unittest.TestCase):
    def test_exact_one_duo_final_review_safety(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "test_final_review.mjs")],
            cwd=root, capture_output=True, text=True, timeout=12, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_pickup_unavailable_does_not_confuse_single_store_with_all(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "test_pickup_availability.mjs")],
            cwd=root, capture_output=True, text=True, timeout=12, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_pickup_choice_accepts_ill_pick_it_up_only(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "test_pickup_choice.mjs")],
            cwd=root, capture_output=True, text=True, timeout=12, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_product_add_to_bag_or_continue(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "test_product_add_to_bag.mjs")],
            cwd=root, capture_output=True, text=True, timeout=12, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_read_only_test_product_pickup_inspector(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "test_pickup_inspector.mjs")],
            cwd=root, capture_output=True, text=True, timeout=12, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_bag_checkout_button_or_link(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "test_bag_checkout.mjs")],
            cwd=root, capture_output=True, text=True, timeout=12, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_security_challenge_guard_keeps_fail_closed(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "test_challenge_check.mjs")],
            cwd=root, capture_output=True, text=True, timeout=12, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_real_browser_selector_logic_with_simulated_controls(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "test_applecare_selector.mjs")],
            cwd=root, capture_output=True, text=True, timeout=12, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
