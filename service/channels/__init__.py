"""
The channel registry. calendar/mufc/markets need external auth, a data
source, or a watchlist not wired up yet. milestone, weather, and f1 are
built — milestone needed only a reference date, weather only a
location, and f1 needs nothing external at all (OpenF1 is free/keyless).

"manual" isn't here: it's not scheduled, it's POST /message, handled
directly in main.py.
"""
from .base import Channel, ChannelMessage
from .f1 import CHANNEL as _f1
from .milestone import CHANNEL as _milestone
from .weather import CHANNEL as _weather

CHANNELS: list[Channel] = [_milestone, _weather, _f1]

__all__ = ["Channel", "ChannelMessage", "CHANNELS"]
