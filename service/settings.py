"""
Runtime settings — things a person changes from the phone form that have to
survive a service restart, as opposed to config.py's constants and env vars.

Currently just the quiet-hours snooze. Reads come from an in-memory cache
because `is_quiet_hours()` runs on every `GET /current`, i.e. every 5 seconds
per renderer, and that shouldn't be a database round trip. Writes go to
SQLite and update the cache in the same call. One uvicorn process owns the
board, so there's no second writer to invalidate the cache underneath us.
"""
from __future__ import annotations

import sqlite3

_SNOOZE_KEY = "quiet_hours_snooze_until"

_snooze_until: float | None = None


def load(conn: sqlite3.Connection) -> None:
    """Populate the cache from the database. Called once at startup."""
    global _snooze_until
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (_SNOOZE_KEY,)).fetchone()
    _snooze_until = float(row["value"]) if row is not None and row["value"] else None


def quiet_snooze_until() -> float | None:
    """Epoch seconds through which quiet hours is suppressed, or None."""
    return _snooze_until


def set_quiet_snooze(conn: sqlite3.Connection, until: float | None) -> None:
    global _snooze_until
    if until is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (_SNOOZE_KEY,))
    else:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_SNOOZE_KEY, str(until)),
        )
    conn.commit()
    _snooze_until = until
