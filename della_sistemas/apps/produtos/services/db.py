from pathlib import Path
import sqlite3

from .config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _col_exists(cur: sqlite3.Cursor, table: str, col: str) -> bool:
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)


def _ensure_stock_moves_deposito_columns() -> None:
    """Migração leve: adiciona deposito_id/deposito_nome em stock_moves se faltarem."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if not _col_exists(cur, "stock_moves", "deposito_id"):
            conn.execute("ALTER TABLE stock_moves ADD COLUMN deposito_id INTEGER")
        if not _col_exists(cur, "stock_moves", "deposito_nome"):
            conn.execute("ALTER TABLE stock_moves ADD COLUMN deposito_nome TEXT")
        conn.commit()
        conn.close()
    except Exception:
        pass


_ensure_stock_moves_deposito_columns()
