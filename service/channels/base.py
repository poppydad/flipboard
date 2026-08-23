"""
Channel plugin interface (build plan §11). A channel is a scheduled job
that decides *what to say* — the layout engine (service/compose/) still
owns geometry, so a channel returns text or a pre-built template grid,
never raw cell codes it assembled by hand.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


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
