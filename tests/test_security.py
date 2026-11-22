import tempfile
import unittest
from pathlib import Path

from mcp_poc import security


class SafeEvalTests(unittest.TestCase):
    def test_basic_math(self):
        self.assertEqual(security.safe_eval("2 + 3 * 4"), 14)
        self.assertEqual(security.safe_eval("(12 + 8) * 3 / 4"), 15)
        self.assertAlmostEqual(security.safe_eval("sqrt(16) + abs(-2)"), 6)

    def test_rejects_code_execution(self):
        for bad in ["__import__('os').system('echo hi')", "open('x')", "().__class__", "a + 1", "lambda: 1", "[1,2]"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                security.safe_eval(bad)

    def test_rejects_resource_exhaustion(self):
        with self.assertRaises(ValueError):
            security.safe_eval("2 ** 10000")
        with self.assertRaises(ValueError):
            security.safe_eval("1" * 500)

    def test_division_by_zero_is_value_error(self):
        with self.assertRaises(ValueError):
            security.safe_eval("1 / 0")


class SafeJoinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "approved"
        self.base.mkdir()
        (self.base / "ok.md").write_text("hello", encoding="utf-8")
        (Path(self.tmp.name) / "secret.txt").write_text("nope", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_allows_plain_file(self):
        self.assertEqual(security.safe_join(self.base, "ok.md").read_text(), "hello")

    def test_blocks_traversal_and_absolute(self):
        for bad in ["../secret.txt", "..\\secret.txt", "/etc/passwd", "sub/ok.md", "ok.md/../../secret.txt"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                security.safe_join(self.base, bad)

    def test_blocks_disallowed_extension_and_missing(self):
        (self.base / "run.sh").write_text("x")
        with self.assertRaises(ValueError):
            security.safe_join(self.base, "run.sh")
        with self.assertRaises(ValueError):
            security.safe_join(self.base, "missing.md")


class SkuTests(unittest.TestCase):
    def test_validate(self):
        self.assertEqual(security.validate_sku(" lap-001 "), "LAP-001")
        for bad in ["LAP001", "'; DROP TABLE products;--", "", "LAPT-001"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                security.validate_sku(bad)


if __name__ == "__main__":
    unittest.main()
