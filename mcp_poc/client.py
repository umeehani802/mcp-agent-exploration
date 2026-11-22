"""MCP *client* built with the official SDK.

`open_session()` is the one place that knows how to reach the server (stdio subprocess or HTTP URL).
Everything else (CLI demo, LangChain agent, offline agent) just uses the returned ClientSession.

Demo:  python -m mcp_poc.client            # spawns the server over stdio
       python -m mcp_poc.client --url http://127.0.0.1:8000/mcp   # connect to a running HTTP server
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl

from .config import ROOT


@asynccontextmanager
async def open_session(url: str | None = None):
    """Yield an initialized ClientSession. `url` -> Streamable HTTP; otherwise spawn the server via stdio."""
    url = url or os.getenv("MCP_SERVER_URL") or None
    if url:
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(url) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()  # MCP handshake: version + capability negotiation
                yield session
    else:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_poc.server"],
            env=dict(os.environ),
            cwd=str(ROOT),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def result_text(result) -> str:
    """Flatten a CallToolResult's content blocks into plain text."""
    return "\n".join(getattr(block, "text", str(block)) for block in result.content)


async def demo(url: str | None) -> None:
    async with open_session(url) as session:
        print("== 1. TOOL DISCOVERY (tools/list) ==")
        tools = (await session.list_tools()).tools
        for t in tools:
            print(f"- {t.name}: {t.description.splitlines()[0] if t.description else ''}")

        print("\n== 2. TOOL CALL: calculate ==")
        print(result_text(await session.call_tool("calculate", {"expression": "(12 + 8) * 3 / 4"})))

        print("\n== 3. TOOL CALL: get_product ==")
        print(result_text(await session.call_tool("get_product", {"sku": "LAP-001"})))

        print("\n== 4. TOOL ERROR HANDLING: bad SKU ==")
        bad = await session.call_tool("get_product", {"sku": "nope"})
        print(f"isError={bad.isError} -> {result_text(bad)}")

        print("\n== 5. SECURITY: path traversal blocked ==")
        sec = await session.call_tool("read_approved_file", {"name": "../private/secrets.txt"})
        print(f"isError={sec.isError} -> {result_text(sec)}")

        print("\n== 6. RESOURCES ==")
        for r in (await session.list_resources()).resources:
            print(f"- {r.uri}")
        summary = await session.read_resource(AnyUrl("inventory://summary"))
        print(summary.contents[0].text)

        print("\n== 7. PROMPTS ==")
        prompt = await session.get_prompt("inventory_report", {"category": "Books"})
        print(prompt.messages[0].content.text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None, help="Streamable HTTP endpoint, e.g. http://127.0.0.1:8000/mcp")
    asyncio.run(demo(ap.parse_args().url))
