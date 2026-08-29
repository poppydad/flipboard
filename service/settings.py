"""
Runtime settings — things a person changes from the phone form that have to
survive a service restart, as opposed to config.py's constants and env vars.

The quiet-hours snooze, and the display's brightness/contrast. Reads come
from an in-memory cache
because `is_quiet_hours()` runs on every `GET /current`, i.e. every 5 seconds
per renderer, and that shouldn't be a database round trip. Writes go to
SQLite and update the cache in the same call. One uvicorn process owns the
board, so there's no second writer to invalidate the cache underneath us.
"""
from __future__ import annotations

import sqlite3

_SNOOZE_KEY = "quiet_hours_snooze_until"
_BRIGHTNESS_KEY = "display_brightness"
_CONTRAST_KEY = "display_contrast"

_snooze_until: float | None = None
# Both are CSS-filter values applied by the renderer to the canvas: 1.0 is
# untouched. They dim the *image*, not the panel backlight — see
# deploy/panel.sh for why that distinction matters here.
_brightness: float = 1.0
_contrast: float = 1.0


def _read(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row is not None else None


def _write(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    else:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    conn.commit()


def load(conn: sqlite3.Connection) -> None:
    """Populate the cache from the database. Called once at startup."""
    global _snooze_until, _brightness, _contrast
    raw = _read(conn, _SNOOZE_KEY)
    _snooze_until = float(raw) if raw else None
    _brightness = float(_read(conn, _BRIGHTNESS_KEY) or 1.0)
    _contrast = float(_read(conn, _CONTRAST_KEY) or 1.0)


def display() -> tuple[float, float]:
    """(brightness, contrast) the board should render at when it's awake."""
    return _brightness, _contrast


def set_display(
    conn: sqlite3.Connection, brightness: float | None = None, contrast: float | None = None
) -> None:
    global _brightness, _contrast
    if brightness is not None:
        _brightness = max(0.0, min(1.0, brightness))
        _write(conn, _BRIGHTNESS_KEY, str(_brightness))
    if contrast is not None:
        _contrast = max(0.0, min(2.0, contrast))
        _write(conn, _CONTRAST_KEY, str(_contrast))


def quiet_snooze_until() -> float | None:
    """Epoch seconds through which quiet hours is suppressed, or None."""
    return _snooze_until


def set_quiet_snooze(conn: sqlite3.Connection, until: float | None) -> None:
    global _snooze_until
    _write(conn, _SNOOZE_KEY, None if until is None else str(until))
    _snooze_until = until
