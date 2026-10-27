import shutil
import subprocess
import unittest
from pathlib import Path


class AppleCareJavaScriptTests(unittest.TestCase):
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
