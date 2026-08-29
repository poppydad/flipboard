"""
Channel plugin interface (build plan §11). A channel is a scheduled job
that decides *what to say* — the layout engine (service/compose/) still
owns geometry, so a channel returns text or a pre-built template grid,
never raw cell codes it assembled by hand.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from datetime import datetime, time as time_of_day, timedelta
from typing import Callable, Optional


def expires_in(hours: float) -> float:
    """An absolute expiry `hours` from now, as an epoch float.

    Every channel message should have one. A reading with no expiry stays
    eligible forever: the 4:30pm weather sat on the board reading 82F at
    11pm, and before that an f1 countdown owned the display for a week.
    `_supersede` only retires the *previous* message when a new one lands —
    it can't help when the channel simply doesn't run again, which is
    exactly the case at night and whenever an API is down.

    Pick a span a bit longer than the polling interval, so a single failed
    fetch doesn't blank the channel but a run of them does.
    """
    return time.time() + hours * 3600


def expires_at_midnight() -> float:
    """End of today — for messages that are about the day itself."""
    return datetime.combine(datetime.now().date(), time_of_day.max).timestamp()


def countdown_parts(remaining: timedelta) -> tuple[str, str]:
    """A timedelta as (number, unit) for the `countdown` template.

    Floors to the largest whole unit, so a fixture 1d22h out reads "1 DAY"
    rather than "2 DAYS" — the same convention f1 has always used. Singular
    is not cosmetic here: the unit gets a whole 22-column row to itself, so
    "1 DAYS" is very legible and very wrong.
    """
    if remaining.days >= 1:
        n, unit = remaining.days, "DAY"
    elif remaining.seconds >= 3600:
        n, unit = remaining.seconds // 3600, "HOUR"
    else:
        n, unit = max(remaining.seconds // 60, 0), "MINUTE"
    return str(n), unit if n == 1 else unit + "S"


@dataclass
class ChannelMessage:
    """What a channel wants posted. Exactly one of text/grid — see messages.create_message."""

    text: str | None = None
    grid: list[int] | None = None
    priority: int = 50
    dwell_seconds: int = 300
    pinned: bool = False
    expires_at: float | None = None


@dataclass
class Channel:
    name: str
    cron: str  # APScheduler crontab expression, e.g. "30 6,16 * * *" for 6:30am and 4pm
    run: Callable[[], Optional[ChannelMessage]]
