"""A from-scratch MCP *client* (stdlib only) that prints every JSON-RPC message.

Run:  python -m mcp_poc.scratch.mini_client
It performs the full lifecycle: initialize -> initialized -> tools/list -> tools/call -> resources -> prompts.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class MiniMCPClient:
    def __init__(self, verbose: bool = False, env: dict | None = None):
        self.verbose = verbose
        self._id = 0
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "mcp_poc.scratch.mini_server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL if not verbose else None,
            text=True, cwd=ROOT, env=env,
        )

    def _send(self, message: dict) -> None:
        if self.verbose:
            print(f"  CLIENT -> SERVER  {json.dumps(message)}")
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed the connection")
        response = json.loads(line)
        if self.verbose:
            print(f"  SERVER -> CLIENT  {line.strip()}")
        return response

    def notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})

    # --- MCP lifecycle ---------------------------------------------------------------
    def initialize(self) -> dict:
        res = self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "mini-mcp-client", "version": "1.0.0"},
        })
        self.notify("notifications/initialized")
        return res["result"]

    def list_tools(self) -> list[dict]:
        return self.request("tools/list")["result"]["tools"]

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def demo() -> None:
    print("=== From-scratch MCP client demo (verbose wire log) ===\n")
    with MiniMCPClient(verbose=True) as c:
        print("\n1) INITIALIZE (capability negotiation)")
        info = c.initialize()
        print(f"   server: {info['serverInfo']}  capabilities: {list(info['capabilities'])}")

        print("\n2) TOOL DISCOVERY (tools/list)")
        for t in c.list_tools():
            print(f"   - {t['name']}: {t['description']}")

        print("\n3) TOOL CALL (tools/call) -> calculate")
        c.call_tool("calculate", {"expression": "(12 + 8) * 3 / 4"})

        print("\n4) TOOL CALL -> get_product (reads SQLite)")
        c.call_tool("get_product", {"sku": "LAP-001"})

        print("\n5) SECURITY: path traversal attempt is rejected")
        c.call_tool("read_approved_file", {"name": "../private/secrets.txt"})

        print("\n6) RESOURCES + PROMPTS")
        c.request("resources/list")
        c.request("resources/read", {"uri": "docs://approved/returns_policy.md"})
        c.request("prompts/get", {"name": "inventory_report", "arguments": {"category": "Books"}})


if __name__ == "__main__":
    demo()
