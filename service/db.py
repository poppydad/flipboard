"""
SQLite storage — single-digit writes a day, Postgres would be a costume.
Schema per build plan §9.
"""
from __future__ import annotations

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

-- selection.py's _pick and _pinned_waiting both correlate every message
-- against MAX(shown_at) for that message. Unindexed that's a full scan of
-- display_log per candidate row, i.e. O(messages x log entries): measured
-- 1.5s per GET /current at three months of real traffic and 24.8s at one
-- year, against a renderer that polls every 5s. With this index the same
-- year's data selects in 34ms.
CREATE INDEX IF NOT EXISTS idx_display_log_message_id ON display_log(message_id);

-- Runtime settings that have to outlive a restart. Currently one key:
-- quiet_hours_snooze_until, an epoch float set by the phone form's "keep the
-- board on" button. CREATE ... IF NOT EXISTS plus executescript on every
-- startup means an already-deployed database picks this up with no migration.
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT
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

    from .messages import create_message

    create_message(conn, source="system", text="FLIPBOARD READY", priority=90, dwell_seconds=300)
