"""
Quiet hours (build plan §11 + the constraints in CLAUDE.md: "there's an
infant in the house" — sound and brightness both need a hard off-switch).

The exact window and whether brightness goes to a dim floor or fully off
(build plan probe 6, never run against real hardware here) are both
placeholders — tune QUIET_HOURS_START/END and BRIGHTNESS_QUIET_FLOOR to
the household's actual schedule. Fully off is the safer default if the
real answer turns out to be "off, not dim."
"""
from __future__ import annotations

from datetime import datetime, time

QUIET_HOURS_START = time(21, 0)  # 9:00pm
QUIET_HOURS_END = time(7, 0)  # 7:00am

BRIGHTNESS_NORMAL = 1.0
BRIGHTNESS_QUIET_FLOOR = 0.0


def is_quiet_hours(now: datetime | None = None) -> bool:
    current = (now or datetime.now()).time()
    if QUIET_HOURS_START <= QUIET_HOURS_END:
        return QUIET_HOURS_START <= current < QUIET_HOURS_END
    # Window wraps past midnight (e.g. 21:00 -> 07:00) — the common case.
    return current >= QUIET_HOURS_START or current < QUIET_HOURS_END
