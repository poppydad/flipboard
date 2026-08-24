"""
Deterministic message selection (build plan §9): pinned wins; else lowest
`priority` among eligible (non-expired, starts_at-reached) candidates;
ties go to least-recently-shown. Holds the current pick for its
dwell_seconds before reselecting — GET /current is what drives this,
since the renderer polls it every 5s and reselection only needs to
happen when that poll notices the dwell has run out.

Quiet hours (build plan §11) narrow eligibility to pinned messages only
— "no channel pushes, pinned manual messages only." That's enforced
here, not by channels skipping themselves, so it applies uniformly no
matter what put a message in the table.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from .config import is_quiet_hours


@dataclass
class _Pick:
    message_id: int
    selected_at: float


class Selector:
    def __init__(self) -> None:
        self._current: _Pick | None = None

    def current(self, conn: sqlite3.Connection, force: bool = False) -> sqlite3.Row | None:
        now = time.time()
        quiet = is_quiet_hours()

        if not force and self._current is not None:
            row = conn.execute(
                "SELECT * FROM messages WHERE id = ?", (self._current.message_id,)
            ).fetchone()
            still_dwelling = (now - self._current.selected_at) < row["dwell_seconds"] if row else False
            # A pinned message means "show now" — it should interrupt an in-progress
            # dwell hold, not wait behind it, even if the pin lands mid-message.
            # This also has to cover pinning over an already-pinned message: without
            # it, "Pin — show now" silently became "queue behind whatever's already
            # pinned" the moment two messages were pinned at once.
            preempted = row is not None and self._pinned_waiting(conn, now, quiet, currently_showing=row)
            if row is not None and self._eligible(row, now, quiet) and still_dwelling and not preempted:
                return row

        picked = self._pick(conn, now, quiet)
        if picked is None:
            self._current = None
            return None

        self._current = _Pick(message_id=picked["id"], selected_at=now)
        conn.execute("INSERT INTO display_log (message_id, shown_at) VALUES (?, ?)", (picked["id"], now))
        conn.commit()
        return picked

    def _pinned_waiting(
        self, conn: sqlite3.Connection, now: float, quiet: bool, *, currently_showing: sqlite3.Row
    ) -> bool:
        """True if some pinned, eligible message should take over from what's
        currently showing. If that's not itself pinned, any eligible pinned
        candidate preempts it (the original rule). If it IS pinned, only a
        candidate that's never been shown preempts — "just pinned" — so two
        pinned messages don't fight over the display on every 5s poll once
        each has had its turn; once shown, normal least-recently-shown
        rotation among pinned messages takes over instead.
        """
        rows = conn.execute(
            "SELECT m.*, (SELECT MAX(shown_at) FROM display_log WHERE message_id = m.id) AS last_shown "
            "FROM messages m WHERE m.pinned = 1"
        ).fetchall()
        showing_is_pinned = bool(currently_showing["pinned"])
        for r in rows:
            if not self._eligible(r, now, quiet):
                continue
            if not showing_is_pinned:
                return True
            if r["id"] != currently_showing["id"] and r["last_shown"] is None:
                return True
        return False

    @staticmethod
    def _eligible(row: sqlite3.Row, now: float, quiet: bool = False) -> bool:
        if quiet and not row["pinned"]:
            return False
        if row["starts_at"] is not None and row["starts_at"] > now:
            return False
        if row["expires_at"] is not None and row["expires_at"] <= now:
            return False
        return True

    def _pick(self, conn: sqlite3.Connection, now: float, quiet: bool) -> sqlite3.Row | None:
        rows = conn.execute(
            """
            SELECT m.*, (
              SELECT MAX(shown_at) FROM display_log WHERE message_id = m.id
            ) AS last_shown
            FROM messages m
            """
        ).fetchall()
        candidates = [r for r in rows if self._eligible(r, now, quiet)]
        if not candidates:
            return None

        pinned = [r for r in candidates if r["pinned"]]
        pool = pinned if pinned else candidates

        # last_shown is an epoch float (or NULL for "never shown") — an explicit
        # Python-side timestamp, not SQLite's CURRENT_TIMESTAMP, which only has
        # 1-second resolution and made rapid reselections (e.g. paginated
        # messages cycling via /next) tie and silently favor the lower id.
        never_shown = -1.0
        pool.sort(key=lambda r: (r["priority"], r["last_shown"] if r["last_shown"] is not None else never_shown))
        return pool[0]
