"""
APScheduler wiring (build plan constraint table: "APScheduler in-process
— one process, one file, systemd keeps it alive"). Each registered
channel (service/channels/CHANNELS) gets a cron job; when it fires, the
channel decides what to say and this module handles posting it — quiet
hours gates here, not in each channel, so no channel has to remember to
check it itself.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import CHANNELS, Channel
from .. import db
from ..config import is_quiet_hours
from ..messages import create_message

logger = logging.getLogger("flipboard.scheduler")

_scheduler: AsyncIOScheduler | None = None


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
