"""A from-scratch MCP server over stdio, using ONLY the Python standard library.

Purpose: show exactly what the official SDK hides. MCP is JSON-RPC 2.0, one JSON message per line
on stdin/stdout. Run it directly and type/paste JSON lines, or use mini_client.py.

    python -m mcp_poc.scratch.mini_server

NOTE: stdout is the protocol channel. Never print() anything else there; log to stderr.
"""
from __future__ import annotations

import json
import sys

from .. import tools_impl as impl
from ..config import get_approved_dir

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "inventory-mini-mcp", "version": "1.0.0"}
TOOLS = {t["name"]: t for t in impl.TOOL_SPECS}

PROMPTS = {
    "inventory_report": {
        "description": "Ask the model to write an inventory report for a category.",
        "arguments": [{"name": "category", "description": "Product category", "required": False}],
    }
}


def log(msg: str) -> None:
    print(f"[mini-mcp] {msg}", file=sys.stderr, flush=True)


# ------------------------------------------------------------------ JSON-RPC helpers
def ok(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def err(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


# ------------------------------------------------------------------ method handlers
def handle_initialize(params):
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}, "resources": {}, "prompts": {}},
        "serverInfo": SERVER_INFO,
    }


def handle_tools_list(params):
    return {"tools": [{k: v for k, v in t.items() if k != "handler"} for t in TOOLS.values()]}


def handle_tools_call(params):
    name = params.get("name")
    args = params.get("arguments") or {}
    if name not in TOOLS:
        raise KeyError(f"Unknown tool: {name}")  # protocol-level error
    try:
        value = TOOLS[name]["handler"](**args)
        return {"content": [{"type": "text", "text": impl.to_text(value)}], "isError": False}
    except (ValueError, TypeError) as exc:
        # Tool *execution* errors are returned as a normal result with isError=true so the LLM can see and recover.
        return {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True}


def handle_resources_list(params):
    return {
        "resources": [
            {"uri": f"docs://approved/{n}", "name": n, "mimeType": "text/plain"}
            for n in impl.list_approved_files()
        ]
        + [{"uri": "inventory://summary", "name": "Inventory summary", "mimeType": "application/json"}]
    }


def handle_resources_read(params):
    uri = params.get("uri", "")
    if uri == "inventory://summary":
        return {"contents": [{"uri": uri, "mimeType": "application/json", "text": impl.to_text(impl.inventory_summary())}]}
    prefix = "docs://approved/"
    if uri.startswith(prefix):
        try:
            text = impl.read_approved_file(uri[len(prefix):])
        except ValueError as exc:
            raise KeyError(str(exc))
        return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]}
    raise KeyError(f"Unknown resource: {uri}")


def handle_prompts_list(params):
    return {"prompts": [{"name": n, **p} for n, p in PROMPTS.items()]}


def handle_prompts_get(params):
    if params.get("name") not in PROMPTS:
        raise KeyError(f"Unknown prompt: {params.get('name')}")
    category = (params.get("arguments") or {}).get("category", "Electronics")
    text = impl.inventory_report_prompt(category)
    return {"description": PROMPTS["inventory_report"]["description"],
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}


METHODS = {
    "initialize": handle_initialize,
    "ping": lambda p: {},
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "resources/list": handle_resources_list,
    "resources/read": handle_resources_read,
    "prompts/list": handle_prompts_list,
    "prompts/get": handle_prompts_get,
}


def process(message: dict):
    """Return a response dict, or None for notifications (no id => no response)."""
    msg_id = message.get("id")
    method = message.get("method")
    if method is None:
        return None  # a response to something we sent; this server sends no requests
    if msg_id is None:  # notification, e.g. notifications/initialized
        log(f"notification: {method}")
        return None
    handler = METHODS.get(method)
    if handler is None:
        return err(msg_id, -32601, f"Method not found: {method}")
    try:
        return ok(msg_id, handler(message.get("params") or {}))
    except KeyError as exc:
        return err(msg_id, -32602, str(exc.args[0]))
    except Exception as exc:  # never crash the server on a bad request
        log(f"internal error: {exc!r}")
        return err(msg_id, -32603, "Internal error")


def main() -> None:
    log(f"started; approved dir = {get_approved_dir()}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps(err(None, -32700, "Parse error")), flush=True)
            continue
        response = process(message)
        if response is not None:
            print(json.dumps(response), flush=True)
    log("stdin closed; shutting down")


if __name__ == "__main__":
    main()
