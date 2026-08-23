"""
Shared message-creation logic: turns text or a pre-built grid into one or
more `messages` rows. Used by both POST /message (source='manual') and
scheduled channels (source=<channel name>) — the two paths for anything
ending up on the board — so pagination and dwell-splitting only happen
in one place.
"""
from __future__ import annotations

import json
import sqlite3

from .compose import CHARSET, COLS, ROWS, render

MIN_PAGE_DWELL_SECONDS = 20


def validate_grid(grid: list[int]) -> None:
    """Checked only at the untrusted boundary (POST /message/grid) — a
    channel building a grid from a template is already trusted to get
    this right, the same reasoning create_message's own callers rely on.
    """
    if len(grid) != ROWS * COLS:
        raise ValueError(f"grid must have exactly {ROWS * COLS} cells, got {len(grid)}")
    bad = [code for code in grid if not (0 <= code < CHARSET.size)]
    if bad:
        raise ValueError(f"invalid charset code(s) {sorted(set(bad))}; must be 0..{CHARSET.size - 1}")


def create_message(
    conn: sqlite3.Connection,
    *,
    source: str,
    text: str | None = None,
    grid: list[int] | None = None,
    priority: int = 50,
    dwell_seconds: int = 300,
    starts_at: float | None = None,
    expires_at: float | None = None,
    pinned: bool = False,
) -> list[int]:
    """Inserts one row per page and returns their ids, in page order.

    Exactly one of `text` or `grid` must be given. `text` runs through
    the layout engine and may paginate into several rows (build plan
    §10's "never truncate silently"); `grid` is a caller-built single
    page (e.g. a channel using a template directly) and is never
    paginated — it's already exactly ROWS*COLS by construction.
    """
    if (text is None) == (grid is None):
        raise ValueError("create_message needs exactly one of text or grid")

    pages = render(text) if text is not None else [grid]
    page_dwell = max(MIN_PAGE_DWELL_SECONDS, dwell_seconds // len(pages))

    ids: list[int] = []
    for page in pages:
        cur = conn.execute(
            "INSERT INTO messages "
            "(source, raw_text, grid, priority, dwell_seconds, starts_at, expires_at, pinned) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (source, text, json.dumps(page), priority, page_dwell, starts_at, expires_at, int(pinned)),
        )
        ids.append(cur.lastrowid)
    conn.commit()
    return ids
