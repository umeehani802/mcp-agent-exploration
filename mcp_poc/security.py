"""Input validation and sandboxing helpers.

These are the *server-side* controls. An MCP server must never trust the model's arguments:
the LLM can be wrong, manipulated by prompt injection, or simply creative.
"""
from __future__ import annotations

import ast
import math
import operator
import re
from pathlib import Path

ALLOWED_EXTENSIONS = {".md", ".txt", ".csv"}
MAX_FILE_BYTES = 100_000
FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
SKU_RE = re.compile(r"^[A-Z]{3}-\d{3}$")


# ----------------------------------------------------------------------------- files
def safe_join(base: Path, name: str) -> Path:
    """Resolve `name` inside `base` or raise ValueError (blocks ../, absolute paths, symlink escapes)."""
    if not isinstance(name, str) or not FILENAME_RE.match(name):
        raise ValueError("Invalid file name. Use a plain file name such as 'returns_policy.md'.")
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    base_resolved = base.resolve()
    target = (base_resolved / name).resolve()
    if base_resolved not in target.parents:
        raise ValueError("Access outside the approved folder is not allowed.")
    if not target.is_file():
        raise ValueError(f"File not found in approved folder: {name}")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("File is too large to return.")
    return target


# ----------------------------------------------------------------------------- inputs
def validate_sku(sku: str) -> str:
    if not isinstance(sku, str) or not SKU_RE.match(sku.strip().upper()):
        raise ValueError("SKU must look like 'ABC-123'.")
    return sku.strip().upper()


# ----------------------------------------------------------------------------- math
_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max}
_CONSTS = {"pi": math.pi, "e": math.e}
MAX_EXPR_LEN = 200
MAX_EXPONENT = 100


def safe_eval(expression: str):
    """Evaluate a *math-only* expression by walking the AST. Never uses eval()/exec()."""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Expression must be a non-empty string.")
    if len(expression) > MAX_EXPR_LEN:
        raise ValueError(f"Expression too long (max {MAX_EXPR_LEN} characters).")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        return _eval_node(tree.body)
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("Could not parse expression.") from exc
    except (ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"Math error: {exc}") from exc


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError(f"Exponent too large (max {MAX_EXPONENT}).")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords or len(node.args) > 5:
            raise ValueError("Unsupported function call arguments.")
        return _FUNCS[node.func.id](*[_eval_node(a) for a in node.args])
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    raise ValueError("Unsupported element in expression (only numbers, + - * / // % **, sqrt, abs, round, min, max, pi, e).")
