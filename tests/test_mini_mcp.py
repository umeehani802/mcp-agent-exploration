"""End-to-end protocol test over real stdio using only the standard library."""
import json
import unittest

from mcp_poc.scratch.mini_client import MiniMCPClient


def text_of(response):
    return response["result"]["content"][0]["text"]


class MiniMCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = MiniMCPClient()
        cls.info = cls.client.initialize()

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_handshake(self):
        self.assertEqual(self.info["serverInfo"]["name"], "inventory-mini-mcp")
        self.assertIn("tools", self.info["capabilities"])

    def test_tool_discovery(self):
        names = {t["name"] for t in self.client.list_tools()}
        self.assertEqual(names, {"calculate", "get_product", "list_products", "convert_currency", "read_approved_file"})
        for tool in self.client.list_tools():
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertNotIn("handler", tool)

    def test_tool_call_success(self):
        res = self.client.call_tool("calculate", {"expression": "2 + 3 * 4"})
        self.assertFalse(res["result"]["isError"])
        self.assertEqual(text_of(res), "14")

    def test_tool_call_reads_database(self):
        res = self.client.call_tool("get_product", {"sku": "LAP-001"})
        self.assertEqual(json.loads(text_of(res))["name"], "UltraBook 14 Laptop")

    def test_tool_execution_error_is_in_band(self):
        res = self.client.call_tool("get_product", {"sku": "bad"})
        self.assertTrue(res["result"]["isError"])
        self.assertIn("Error", text_of(res))

    def test_path_traversal_blocked(self):
        res = self.client.call_tool("read_approved_file", {"name": "../private/secrets.txt"})
        self.assertTrue(res["result"]["isError"])
        self.assertNotIn("DUMMY SECRET", text_of(res))

    def test_unknown_tool_is_protocol_error(self):
        res = self.client.call_tool("drop_database", {})
        self.assertEqual(res["error"]["code"], -32602)

    def test_unknown_method(self):
        self.assertEqual(self.client.request("nope/nothing")["error"]["code"], -32601)

    def test_resources_and_prompts(self):
        uris = {r["uri"] for r in self.client.request("resources/list")["result"]["resources"]}
        self.assertIn("docs://approved/returns_policy.md", uris)
        self.assertIn("inventory://summary", uris)
        body = self.client.request("resources/read", {"uri": "docs://approved/returns_policy.md"})
        self.assertIn("14 days", body["result"]["contents"][0]["text"])
        prompt = self.client.request("prompts/get", {"name": "inventory_report", "arguments": {"category": "Books"}})
        self.assertIn("Books", prompt["result"]["messages"][0]["content"]["text"])


if __name__ == "__main__":
    unittest.main()
