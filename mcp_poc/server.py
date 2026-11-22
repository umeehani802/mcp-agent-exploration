"""MCP server built with the OFFICIAL Python SDK (FastMCP).

Exposes the three MCP server primitives:
  * Tools      - model-controlled actions        (calculate, get_product, ...)
  * Resources  - application-controlled context  (inventory://summary, docs://approved/{name})
  * Prompts    - user-controlled templates        (inventory_report)

Run locally over stdio (default; a client spawns this process):
    python -m mcp_poc.server
Run as a remote-style HTTP server (Streamable HTTP, endpoint /mcp):
    python -m mcp_poc.server --transport http
"""
from __future__ import annotations

import argparse
import os
import sys

from mcp.server.fastmcp import FastMCP

from . import tools_impl as impl

mcp = FastMCP(
    "inventory-demo",
    instructions=(
        "Read-only demo server for a small product inventory. Use get_product / list_products for "
        "inventory questions, calculate for arithmetic, convert_currency for currency math, and "
        "read_approved_file for policy documents."
    ),
    host=os.getenv("MCP_HOST", "127.0.0.1"),  # bind to localhost only (DNS-rebinding / exposure safety)
    port=int(os.getenv("MCP_PORT", "8000")),
)


# ------------------------------------------------------------------ TOOLS
@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a math expression safely, e.g. '(12 + 8) * 3 / 4'. Supports + - * / // % **, sqrt, abs, round, min, max."""
    return impl.calculate(expression)


@mcp.tool()
def get_product(sku: str) -> dict:
    """Look up one product by SKU (format ABC-123) in the inventory database. Returns name, category, price, stock."""
    return impl.get_product(sku)


@mcp.tool()
def list_products(category: str | None = None, in_stock_only: bool = False, limit: int = 20) -> list[dict]:
    """List products, optionally filtered by category (Electronics, Furniture, Books, Clearance) and/or in-stock only."""
    return impl.list_products(category, in_stock_only, limit)


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert an amount between USD, EUR, GBP, PKR, INR, JPY using fixed demo rates."""
    return impl.convert_currency(amount, from_currency, to_currency)


@mcp.tool()
def read_approved_file(name: str) -> str:
    """Read a text document from the approved folder (returns_policy.md, shipping_faq.md, store_hours.txt)."""
    return impl.read_approved_file(name)


# ------------------------------------------------------------------ RESOURCES
@mcp.resource("inventory://summary", mime_type="application/json")
def inventory_summary() -> str:
    """Per-category product counts, total units and out-of-stock counts."""
    return impl.to_text(impl.inventory_summary())


@mcp.resource("docs://approved/{name}", mime_type="text/plain")
def approved_document(name: str) -> str:
    """An approved policy/FAQ document, addressed by file name."""
    return impl.read_approved_file(name)


# ------------------------------------------------------------------ PROMPTS
@mcp.prompt()
def inventory_report(category: str = "Electronics") -> str:
    """Template that asks the model to produce a restock report for a category."""
    return impl.inventory_report_prompt(category)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory demo MCP server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    args = parser.parse_args()
    # IMPORTANT: with stdio, stdout is the protocol channel - log to stderr only.
    print(f"[inventory-demo] starting with transport={args.transport}", file=sys.stderr, flush=True)
    mcp.run(transport="stdio" if args.transport == "stdio" else "streamable-http")


if __name__ == "__main__":
    main()
