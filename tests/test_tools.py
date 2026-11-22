import os
import tempfile
import unittest
from pathlib import Path

from mcp_poc import database, tools_impl as t


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = {k: os.environ.get(k) for k in ("MCP_DEMO_DB", "MCP_DEMO_APPROVED_DIR")}
        os.environ["MCP_DEMO_DB"] = str(Path(self.tmp.name) / "inv.db")
        approved = Path(self.tmp.name) / "approved"
        approved.mkdir()
        (approved / "a.md").write_text("doc a", encoding="utf-8")
        os.environ["MCP_DEMO_APPROVED_DIR"] = str(approved)
        database.init_db()

    def tearDown(self):
        for k, v in self._old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.tmp.cleanup()

    def test_calculate(self):
        self.assertEqual(t.calculate("(12 + 8) * 3 / 4"), "15")
        self.assertEqual(t.calculate("10 / 4"), "2.5")

    def test_get_product(self):
        p = t.get_product("lap-001")
        self.assertEqual(p["sku"], "LAP-001")
        self.assertEqual(p["stock"], 12)
        with self.assertRaises(ValueError):
            t.get_product("ZZZ-999")

    def test_sql_injection_is_inert(self):
        with self.assertRaises(ValueError):
            t.get_product("LAP-001' OR '1'='1")
        self.assertEqual(t.list_products(category="Books' OR '1'='1"), [])

    def test_list_products_filters(self):
        self.assertEqual({p["category"] for p in t.list_products(category="books")}, {"Books"})
        self.assertTrue(all(p["stock"] > 0 for p in t.list_products(in_stock_only=True)))
        with self.assertRaises(ValueError):
            t.list_products(limit=1000)

    def test_database_is_read_only(self):
        con = database.connect_readonly()
        with self.assertRaises(Exception):
            con.execute("DELETE FROM products")
        con.close()

    def test_convert_currency(self):
        r = t.convert_currency(250, "usd", "pkr")
        self.assertEqual(r["result"], 70000.0)
        with self.assertRaises(ValueError):
            t.convert_currency(1, "USD", "XYZ")
        with self.assertRaises(ValueError):
            t.convert_currency(-5, "USD", "PKR")

    def test_files(self):
        self.assertEqual(t.list_approved_files(), ["a.md"])
        self.assertEqual(t.read_approved_file("a.md"), "doc a")
        with self.assertRaises(ValueError):
            t.read_approved_file("../inv.db")

    def test_summary(self):
        cats = {c["category"]: c for c in t.inventory_summary()["categories"]}
        self.assertEqual(cats["Books"]["units"], 93)


if __name__ == "__main__":
    unittest.main()
