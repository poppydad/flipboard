"""
Deterministic message selection (build plan §9): pinned wins; else lowest
`priority` among eligible (non-expired, starts_at-reached) candidates;
ties go to least-recently-shown. Holds the current pick for its
dwell_seconds before reselecting — GET /current is what drives this,
since the renderer polls it every 5s and reselection only needs to
happen when that poll notices the dwell has run out.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass


@dataclass
class _Pick:
    message_id: int
    selected_at: float


class Selector:
    def __init__(self) -> None:
        self._current: _Pick | None = None

    def current(self, conn: sqlite3.Connection, force: bool = False) -> sqlite3.Row | None:
        now = time.time()

        if not force and self._current is not None:
            row = conn.execute(
                "SELECT * FROM messages WHERE id = ?", (self._current.message_id,)
            ).fetchone()
            still_dwelling = (now - self._current.selected_at) < row["dwell_seconds"] if row else False
            # A pinned message means "show now" — it should interrupt an in-progress
            # dwell hold, not wait behind it, even if the pin lands mid-message.
            preempted = row is not None and not row["pinned"] and self._pinned_waiting(conn, now)
            if row is not None and self._eligible(row, now) and still_dwelling and not preempted:
                return row

        picked = self._pick(conn, now)
        if picked is None:
            self._current = None
            return None

        self._current = _Pick(message_id=picked["id"], selected_at=now)
        conn.execute("INSERT INTO display_log (message_id) VALUES (?)", (picked["id"],))
        conn.commit()
        return picked

    def _pinned_waiting(self, conn: sqlite3.Connection, now: float) -> bool:
        rows = conn.execute("SELECT * FROM messages WHERE pinned = 1").fetchall()
        return any(self._eligible(r, now) for r in rows)

    @staticmethod
    def _eligible(row: sqlite3.Row, now: float) -> bool:
        if row["starts_at"] is not None and row["starts_at"] > now:
            return False
        if row["expires_at"] is not None and row["expires_at"] <= now:
            return False
        return True

    def _pick(self, conn: sqlite3.Connection, now: float) -> sqlite3.Row | None:
        rows = conn.execute(
            """
            SELECT m.*, (
              SELECT MAX(shown_at) FROM display_log WHERE message_id = m.id
            ) AS last_shown
            FROM messages m
            """
        ).fetchall()
        candidates = [r for r in rows if self._eligible(r, now)]
        if not candidates:
            return None

        pinned = [r for r in candidates if r["pinned"]]
        pool = pinned if pinned else candidates

        # last_shown is a SQLite CURRENT_TIMESTAMP string (or NULL for "never") —
        # lexicographic order matches chronological order, and NULL/"" sorts first.
        pool.sort(key=lambda r: (r["priority"], r["last_shown"] or ""))
        return pool[0]
