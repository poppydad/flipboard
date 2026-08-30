"""
APScheduler wiring (build plan constraint table: "APScheduler in-process
— one process, one file, systemd keeps it alive"). Each registered
channel (service/channels/CHANNELS) gets a cron job; when it fires, the
channel decides what to say and this module handles posting it — quiet
hours gates here, not in each channel, so no channel has to remember to
check it itself. Superseding the channel's previous message happens here
for the same reason (see _supersede).
"""
from __future__ import annotations

import json
import logging
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import CHANNELS, Channel
from .. import db
from ..config import is_quiet_hours
from ..messages import create_message

logger = logging.getLogger("flipboard.scheduler")

_scheduler: AsyncIOScheduler | None = None


def _supersede(conn, source: str, now: float) -> int:
    """Expires a channel's still-live messages so its newest one replaces
    them rather than queueing behind them.

    A cron firing is a *poll*, not necessarily new information: f1 polls
    hourly but its countdown only changes ~37 times across the 14 days
    before a race, so 89% of its posts are exact duplicates of the row
    already in the table. Without this, every poll left a permanent row
    (27/day across the three channels), and because `_pick` ties every
    never-shown row at last_shown = -1.0 and sorts stably, the *lowest
    id* — the stalest countdown — won every time. A board counting down
    to a race would sit on "14 DAYS" for two hours, take 28 hours to
    drain, and starve manual messages, which sit at priority 50 behind
    f1's 15.

    Scoped by `source`, so POST /message is untouched: only a channel
    supersedes its own output. Runs in the same transaction as the
    insert that follows (create_message commits both), so a channel is
    never left with its old message expired and no new one in place.
    """
    cur = conn.execute(
        "UPDATE messages SET expires_at = ? "
        "WHERE source = ? AND (expires_at IS NULL OR expires_at > ?)",
        (now, source, now),
    )
    return cur.rowcount


def _refresh_if_unchanged(conn, channel: Channel, message, now: float) -> bool:
    """If the channel's live message already says exactly this, just push its
    expiry out and report that nothing needs inserting.

    Matters most for the five-minute live-score polls: a match sits at the
    same scoreline for most of its length, and without this every poll would
    retire the current row and insert an identical one. That resets
    `last_shown` to never-shown on every cycle, which distorts the
    round-robin, and it writes ~150 rows an afternoon to say one thing.

    Extending the expiry rather than leaving it alone is the point — the
    message stays *current* precisely because we just re-confirmed it.
    """
    row = conn.execute(
        "SELECT id, grid, raw_text, pinned FROM messages "
        "WHERE source = ? AND (expires_at IS NULL OR expires_at > ?) "
        "ORDER BY id DESC LIMIT 1",
        (channel.name, now),
    ).fetchone()
    if row is None:
        return False

    same = (
        row["raw_text"] == message.text
        and bool(row["pinned"]) == message.pinned
        and (message.grid is None or json.loads(row["grid"]) == message.grid)
    )
    if not same:
        return False

    conn.execute("UPDATE messages SET expires_at = ? WHERE id = ?", (message.expires_at, row["id"]))
    conn.commit()
    return True


def run_channel(channel: Channel) -> None:
    """Runs one channel's job. Exposed at module level (not nested in
    start_scheduler) so it's directly unit-testable without spinning up
    a real scheduler."""
    if is_quiet_hours():
        logger.info("skipping channel %r — quiet hours", channel.name)
        return

    try:
        message = channel.run()
    except Exception:
        logger.exception("channel %r raised, skipping this cycle", channel.name)
        return

    if message is None:
        return

    conn = db.get_connection()
    try:
        now = time.time()
        if _refresh_if_unchanged(conn, channel, message, now):
            return
        superseded = _supersede(conn, channel.name, time.time())
        if superseded:
            logger.info("channel %r superseded %d previous message(s)", channel.name, superseded)
        create_message(
            conn,
            source=channel.name,
            text=message.text,
            grid=message.grid,
            priority=message.priority,
            dwell_seconds=message.dwell_seconds,
            expires_at=message.expires_at,
            pinned=message.pinned,
        )
    finally:
        conn.close()


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    for channel in CHANNELS:
        _scheduler.add_job(
            run_channel,
            CronTrigger.from_crontab(channel.cron),
            args=[channel],
            id=channel.name,
            replace_existing=True,
        )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
