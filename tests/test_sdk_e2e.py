"""End-to-end test of the OFFICIAL-SDK server + client. Skipped automatically if `mcp` is not installed."""
import asyncio
import importlib.util
import unittest

HAS_MCP = importlib.util.find_spec("mcp") is not None


@unittest.skipUnless(HAS_MCP, "mcp SDK not installed (pip install -r requirements.txt)")
class SdkEndToEnd(unittest.TestCase):
    def test_full_flow(self):
        from mcp_poc.client import open_session, result_text

        async def scenario():
            async with open_session() as s:
                names = {t.name for t in (await s.list_tools()).tools}
                self.assertEqual(names, {"calculate", "get_product", "list_products", "convert_currency", "read_approved_file"})
                self.assertEqual(result_text(await s.call_tool("calculate", {"expression": "2+3*4"})), "14")
                bad = await s.call_tool("read_approved_file", {"name": "../private/secrets.txt"})
                self.assertTrue(bad.isError)
                self.assertNotIn("DUMMY SECRET", result_text(bad))
                prompts = {p.name for p in (await s.list_prompts()).prompts}
                self.assertIn("inventory_report", prompts)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
