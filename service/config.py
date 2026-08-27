"""
Quiet hours (build plan §11 + the constraints in CLAUDE.md: "there's an
infant in the house" — sound and brightness both need a hard off-switch).

Window is the household's actual schedule: 8:00pm to 7:00am. Whether
brightness goes to a dim floor or fully off (build plan probe 6, never
run against real hardware here) is still a placeholder — fully off is
the safer default until that's decided on the real display.
"""
from __future__ import annotations

import os
from datetime import datetime, time

QUIET_HOURS_START = time(20, 0)  # 8:00pm
QUIET_HOURS_END = time(7, 0)  # 7:00am

# Escape hatch for demos and daytime-of-the-wrong-kind testing: setting
# FLIPBOARD_QUIET_HOURS=off in the environment makes is_quiet_hours() always
# False. Read once at import, so flipping it means restarting the service —
# deliberate. Editing the window above to fake this works too but is a code
# change you then have to remember to revert; this isn't.
QUIET_HOURS_ENABLED = os.environ.get("FLIPBOARD_QUIET_HOURS", "on").strip().lower() not in {
    "off",
    "0",
    "false",
    "no",
}

BRIGHTNESS_NORMAL = 1.0
BRIGHTNESS_QUIET_FLOOR = 0.0


def is_quiet_hours(now: datetime | None = None) -> bool:
    if not QUIET_HOURS_ENABLED:
        return False
    current = (now or datetime.now()).time()
    if QUIET_HOURS_START <= QUIET_HOURS_END:
        return QUIET_HOURS_START <= current < QUIET_HOURS_END
    # Window wraps past midnight (e.g. 20:00 -> 07:00) — the common case.
    return current >= QUIET_HOURS_START or current < QUIET_HOURS_END
