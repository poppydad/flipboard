"""
milestone channel (build plan §11): a days-old counter as a single
banner line, once a day at 8:00am. No external API — just a reference
date and today's date.
"""
from __future__ import annotations

from datetime import date

from ..compose.templates import banner
from .base import Channel, ChannelMessage

REFERENCE_DATE = date(2025, 11, 8)


def run() -> ChannelMessage:
    days = (date.today() - REFERENCE_DATE).days
    grid = banner(f"{days} DAYS OLD")
    return ChannelMessage(grid=grid, priority=30, dwell_seconds=300)


CHANNEL = Channel(name="milestone", cron="0 8 * * *", run=run)
