"""Tiny SQLite 'business system' used as the external system behind the tools."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import get_db_path

SEED = [
    ("LAP-001", "UltraBook 14 Laptop", "Electronics", 899.00, 12),
    ("LAP-002", "GameStation 17 Laptop", "Electronics", 1499.00, 0),
    ("PHN-001", "Nova X Smartphone", "Electronics", 599.00, 25),
    ("HDP-001", "NoiseCancel Pro Headphones", "Electronics", 199.00, 40),
    ("DSK-001", "Standing Desk 140cm", "Furniture", 349.00, 8),
    ("CHR-001", "Ergonomic Office Chair", "Furniture", 229.00, 15),
    ("BKS-001", "Python for Data Analysis", "Books", 39.00, 60),
    ("BKS-002", "Designing Data-Intensive Apps", "Books", 49.00, 33),
    ("OLD-001", "Last-Gen Tablet", "Clearance", 99.00, 3),
    ("OLD-002", "Wired Mouse (open box)", "Clearance", 9.00, 0),
]


def init_db(path: Path | None = None) -> Path:
    """Create and seed the database if it does not exist (idempotent)."""
    path = Path(path or get_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS products ("
            "sku TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, "
            "price REAL NOT NULL, stock INTEGER NOT NULL)"
        )
        if con.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            con.executemany("INSERT INTO products VALUES (?,?,?,?,?)", SEED)
        con.commit()
    finally:
        con.close()
    return path


def connect_readonly() -> sqlite3.Connection:
    """Open the DB read-only: even a bug or injection cannot modify data."""
    path = init_db()
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con
