"""Central configuration. Paths are resolved at call time so tests can override them via env vars."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get_db_path() -> Path:
    return Path(os.getenv("MCP_DEMO_DB", ROOT / "data" / "inventory.db"))


def get_approved_dir() -> Path:
    return Path(os.getenv("MCP_DEMO_APPROVED_DIR", ROOT / "data" / "approved"))
