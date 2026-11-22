"""Offline "agent" - NO LLM and NO API key needed.

A small rule-based planner stands in for the LLM so you can see the *MCP* part of the flow end to end:
discover tools -> choose a tool -> call it over MCP -> read the result. A real LLM (agent_langchain.py)
replaces the rule-based `plan()` with its own reasoning; everything else is identical.

Run:  python -m mcp_poc.agent_offline "Convert 250 USD to PKR"
"""
from __future__ import annotations

import argparse
import asyncio
import re

from .client import open_session, result_text

SKU = re.compile(r"\b[A-Za-z]{3}-\d{3}\b")
MATH = re.compile(r"(?:calculate|compute|what is)?\s*([\d\.\s\(\)\+\-\*/%]+\d[\d\.\s\(\)\+\-\*/%]*)", re.I)
MONEY = re.compile(r"(\d+(?:\.\d+)?)\s*([A-Za-z]{3})\s+(?:to|in|into)\s+([A-Za-z]{3})", re.I)


def plan(question: str, available: set[str]):
    """Return (tool_name, arguments) or None. Only picks tools that were actually *discovered*."""
    q = question.lower()
    if m := MONEY.search(question):
        choice = ("convert_currency", {"amount": float(m[1]), "from_currency": m[2], "to_currency": m[3]})
    elif m := SKU.search(question):
        choice = ("get_product", {"sku": m[0].upper()})
    elif any(w in q for w in ("policy", "return", "refund", "shipping", "delivery", "hours")):
        name = "returns_policy.md" if any(w in q for w in ("return", "refund", "policy")) else (
            "store_hours.txt" if "hours" in q else "shipping_faq.md")
        choice = ("read_approved_file", {"name": name})
    elif any(w in q for w in ("list", "show", "products", "in stock", "inventory")):
        category = next((c for c in ("Electronics", "Furniture", "Books", "Clearance") if c.lower() in q), None)
        choice = ("list_products", {"category": category, "in_stock_only": "in stock" in q})
    elif (m := MATH.search(question)) and re.search(r"\d\s*[\+\-\*/%]\s*\d|\(", question):
        choice = ("calculate", {"expression": m[1].strip()})
    else:
        return None
    return choice if choice[0] in available else None


async def run(question: str, url: str | None) -> None:
    async with open_session(url) as session:
        tools = (await session.list_tools()).tools  # TOOL DISCOVERY
        print("Discovered MCP tools:", ", ".join(t.name for t in tools))
        print(f"\n[USER]  {question}")
        choice = plan(question, {t.name for t in tools})  # TOOL SELECTION (rule-based stand-in for an LLM)
        if not choice:
            print("[AGENT] I don't have a tool for that.")
            return
        name, args = choice
        print(f"[AGENT] selects tool {name} args={args}")
        result = await session.call_tool(name, args)  # TOOL CALL via MCP client -> server
        print(f"[MCP RESULT] isError={result.isError}\n{result_text(result)}")  # RESULT back to the agent


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default="Convert 250 USD to PKR")
    ap.add_argument("--url", default=None)
    args = ap.parse_args()
    asyncio.run(run(args.question, args.url))
