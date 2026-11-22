"""Transport-independent business logic for every tool/resource/prompt.

Both servers (the official-SDK one in server.py and the from-scratch one in scratch/mini_server.py)
import from here, so the behaviour is identical and unit-testable without any MCP library.
Every function raises ValueError for bad input; MCP layers turn that into `isError: true`.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import security
from .config import get_approved_dir
from .database import connect_readonly

# Fixed, illustrative rates (USD base) standing in for a "test API". Deterministic on purpose.
RATES_PER_USD = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "PKR": 280.0, "INR": 83.0, "JPY": 150.0}


# ------------------------------------------------------------------ tools
def calculate(expression: str) -> str:
    """Evaluate a math expression, e.g. '(12 + 8) * 3 / 4'."""
    result = security.safe_eval(expression)
    return format(result, ".10g") if isinstance(result, float) else str(result)


def get_product(sku: str) -> dict:
    """Look up one product by SKU (format ABC-123) in the inventory database."""
    sku = security.validate_sku(sku)
    con = connect_readonly()
    try:
        row = con.execute("SELECT sku, name, category, price, stock FROM products WHERE sku = ?", (sku,)).fetchone()
    finally:
        con.close()
    if row is None:
        raise ValueError(f"No product with SKU {sku}.")
    return dict(row)


def list_products(category: str | None = None, in_stock_only: bool = False, limit: int = 20) -> list[dict]:
    """List products, optionally filtered by category and/or stock. `limit` is 1-50."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise ValueError("limit must be an integer between 1 and 50.")
    sql, params = "SELECT sku, name, category, price, stock FROM products WHERE 1=1", []
    if category:
        if not isinstance(category, str) or len(category) > 40:
            raise ValueError("Invalid category.")
        sql += " AND category = ? COLLATE NOCASE"
        params.append(category)
    if in_stock_only:
        sql += " AND stock > 0"
    sql += " ORDER BY sku LIMIT ?"
    params.append(limit)
    con = connect_readonly()
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert between USD, EUR, GBP, PKR, INR, JPY using fixed demo rates."""
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0 or amount > 1e12:
        raise ValueError("amount must be a non-negative number.")
    src, dst = str(from_currency).upper(), str(to_currency).upper()
    for code in (src, dst):
        if code not in RATES_PER_USD:
            raise ValueError(f"Unsupported currency {code}. Supported: {sorted(RATES_PER_USD)}")
    value = amount / RATES_PER_USD[src] * RATES_PER_USD[dst]
    return {"amount": amount, "from": src, "to": dst, "result": round(value, 2), "note": "fixed demo rates"}


def list_approved_files() -> list[str]:
    base = get_approved_dir()
    return sorted(p.name for p in base.iterdir() if p.is_file() and p.suffix.lower() in security.ALLOWED_EXTENSIONS)


def read_approved_file(name: str) -> str:
    """Read a text document from the approved folder (e.g. 'returns_policy.md')."""
    return security.safe_join(get_approved_dir(), name).read_text(encoding="utf-8")


# ------------------------------------------------------------------ resources / prompts
def inventory_summary() -> dict:
    con = connect_readonly()
    try:
        rows = con.execute(
            "SELECT category, COUNT(*) AS products, SUM(stock) AS units, "
            "SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) AS out_of_stock "
            "FROM products GROUP BY category ORDER BY category"
        ).fetchall()
    finally:
        con.close()
    return {"categories": [dict(r) for r in rows]}


def inventory_report_prompt(category: str = "Electronics") -> str:
    return (
        f"You are an inventory analyst. Use the available tools to list products in the "
        f"'{category}' category, identify items that are out of stock or low (<5 units), "
        f"and write a short report with a recommended restock list."
    )


# ------------------------------------------------------------------ registry (used by the mini server)
TOOL_SPECS = [
    {
        "name": "calculate",
        "description": "Evaluate a math expression safely, e.g. '(12 + 8) * 3 / 4'.",
        "inputSchema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
        "handler": calculate,
    },
    {
        "name": "get_product",
        "description": "Look up one product by SKU (format ABC-123) in the inventory database.",
        "inputSchema": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]},
        "handler": get_product,
    },
    {
        "name": "list_products",
        "description": "List products, optionally filtered by category and/or in-stock only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "in_stock_only": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            },
        },
        "handler": list_products,
    },
    {
        "name": "convert_currency",
        "description": "Convert an amount between USD, EUR, GBP, PKR, INR, JPY using fixed demo rates.",
        "inputSchema": {
            "type": "object",
            "properties": {"amount": {"type": "number"}, "from_currency": {"type": "string"}, "to_currency": {"type": "string"}},
            "required": ["amount", "from_currency", "to_currency"],
        },
        "handler": convert_currency,
    },
    {
        "name": "read_approved_file",
        "description": "Read a text document from the approved folder (e.g. 'returns_policy.md').",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        "handler": read_approved_file,
    },
]


def to_text(value) -> str:
    """Serialize a tool result the way MCP puts it into a text content block."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
