"""
SQLite storage — single-digit writes a day, Postgres would be a costume.
Schema per build plan §9.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "flipboard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id            INTEGER PRIMARY KEY,
  source        TEXT NOT NULL,
  raw_text      TEXT,
  grid          TEXT NOT NULL,
  priority      INTEGER DEFAULT 50,
  dwell_seconds INTEGER DEFAULT 300,
  starts_at     REAL,
  expires_at    REAL,
  pinned        BOOLEAN DEFAULT 0,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS display_log (
  id INTEGER PRIMARY KEY,
  message_id INTEGER REFERENCES messages(id),
  shown_at REAL NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        _seed_default(conn)
    finally:
        conn.close()


def _seed_default(conn: sqlite3.Connection) -> None:
    """An empty board on first run is a confusing default — seed one low-priority message."""
    row = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()
    if row["n"] > 0:
        return

    from .compose import render

    text = "FLIPBOARD READY"
    conn.execute(
        "INSERT INTO messages (source, raw_text, grid, priority, dwell_seconds, pinned) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("system", text, json.dumps(render(text)[0]), 90, 300, 0),
    )
    conn.commit()
