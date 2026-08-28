"""
Channel plugin interface (build plan §11). A channel is a scheduled job
that decides *what to say* — the layout engine (service/compose/) still
owns geometry, so a channel returns text or a pre-built template grid,
never raw cell codes it assembled by hand.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional


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
