"""
The channel registry. Populated as channels get built — weather,
calendar, f1, mufc, markets, milestone (build plan §11) — each needing
external API access or personal data not wired up yet. Empty for now.

"manual" isn't here: it's not scheduled, it's POST /message, handled
directly in main.py.
"""
from .base import Channel, ChannelMessage

CHANNELS: list[Channel] = []

__all__ = ["Channel", "ChannelMessage", "CHANNELS"]
