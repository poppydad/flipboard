"""
The channel registry. calendar and markets still need external auth, a
data source, or a watchlist not wired up yet. milestone, weather, f1 and
mufc are built — milestone needed only a reference date, weather only a
location, and f1/mufc need nothing external at all (OpenF1 and ESPN's
site API are both free and keyless).

"manual" isn't here: it's not scheduled, it's POST /message, handled
directly in main.py.
"""
from .base import Channel, ChannelMessage
from .f1 import CHANNEL as _f1
from .milestone import CHANNEL as _milestone
from .mufc import CHANNEL as _mufc
from .weather import CHANNEL as _weather

CHANNELS: list[Channel] = [_milestone, _weather, _f1, _mufc]

__all__ = ["Channel", "ChannelMessage", "CHANNELS"]
