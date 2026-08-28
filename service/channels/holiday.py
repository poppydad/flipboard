"""
holiday channel (an addition to build plan §11): a greeting and a piece of
chip art on the day of each of thirteen festivals.

**Dates are a baked-in table, not a live lookup.** These are lunar and move
every year, so they can't be computed from the Gregorian date, but they are
also published years ahead — and the one morning this channel matters is
exactly the morning you don't want a network hiccup to lose. The table came
from Google's public Indian-holidays iCal feed
(`en.indian#holiday@group.v.calendar.google.com`), which is free and
keyless if it ever needs regenerating, and itself only runs to 2031.

**The two Eid dates are approximate.** They depend on an actual moon
sighting, which is why the feed marks future ones "(tentative)"; the
observed date can land a day either side of what's in the table here.

**It runs out after 2031.** `run()` then simply posts nothing, every day,
silently — which is the safe failure but not an obvious one. If the board
stops greeting anyone, look here first.

On the art: the board is 6 rows of 22 flat-coloured cells, so these are
silhouettes read from across a room, not pictures. They're deliberately
symbols rather than figures — a lamp, a thread, a trident, a sweet — both
because a deity rendered in 132 squares would look crude, and because
symbols survive the resolution.
"""
from __future__ import annotations

from datetime import date, datetime, time

from ..compose.art import caption, from_rows
from .base import Channel, ChannelMessage

# --- the art ------------------------------------------------------------
# Each is six rows of exactly 22 palette keys (see compose/art.py):
#   . blank   R red   O orange   Y yellow   G green   B blue   V violet
# One row in each is left blank for the caption to land on.

# A row of four diyas: yellow flame, orange bowl, red base.
_DIWALI = [
    "......................",
    "......................",  # caption
    "......................",
    "...Y....Y....Y....Y...",
    "..OOO..OOO..OOO..OOO..",
    "..RRR..RRR..RRR..RRR..",
]

# Thrown colour, thinning out around the greeting.
_HOLI = [
    "..R...Y....G...V...B..",
    "....O....B....R....V..",
    "......................",  # caption
    "..V....G....Y....O....",
    "...Y...V....O...G.....",
    "..B....R....G....Y....",
]

# The rakhi itself: a thread across the board, knotted at a flower.
_RAKHI = [
    "......................",
    "......................",  # caption
    ".........V.V..........",
    "RRRRRRRRRVYVRRRRRRRRRR",
    ".........V.V..........",
    "......................",
]

# A modak — the sweet, not the deity.
_GANESH = [
    "......................",
    "......................",  # caption
    "..........YY..........",
    "........YYYYYY........",
    ".......YYYYYYYY.......",
    "......OOOOOOOOOO......",
]

# Durga's trishul.
_DURGA = [
    "........Y.Y.Y.........",
    "........YYYYY.........",
    "..........R...........",
    "..........R...........",
    "..........R...........",
    "......................",  # caption
]

# Rama's bow, drawn and pointing right.
_DUSSEHRA = [
    ".......YY.............",
    "......Y...............",
    ".....YRRRRRRRRRRW.....",
    "......Y...............",
    ".......YY.............",
    "......................",  # caption
]

# Nine nights: two dandiya sticks crossed for the garba.
_NAVRATRI = [
    "......................",  # caption
    "........V.....O.......",
    ".........V...O........",
    "..........VO..........",
    ".........O...V........",
    "........O.....V.......",
]

# A peacock feather — Krishna's crown, and the one thing on this board that
# gets to use green, blue and violet together.
_JANMASHTAMI = [
    "......................",  # caption
    ".........GBG..........",
    "........GBVBG.........",
    ".........GBG..........",
    "..........G...........",
    "..........G...........",
]

# Surya. Pongal is a sun festival before it is anything else.
_PONGAL = [
    "......................",  # caption
    "........O.O.O.........",
    ".........YYY..........",
    "......O.YYYYY.O.......",
    ".........YYY..........",
    "........O.O.O.........",
]

# A pookalam — the flower carpet, as concentric rings.
_ONAM = [
    "......................",  # caption
    "........VVVVVV........",
    "......VVYYYYYYVV......",
    ".....VVYYRRRRYYVV.....",
    "......VVYYYYYYVV......",
    "........VVVVVV........",
]

# Crescent and star.
_EID = [
    "......................",  # caption
    "........WWW...........",
    ".......WW.....Y.......",
    ".......WW....YYY......",
    "........WWW...Y.......",
    "......................",
]

# A tree with a star on top.
_CHRISTMAS = [
    "......................",  # caption
    "..........Y...........",
    ".........GGG..........",
    "........GGGGG.........",
    ".......GGGGGGG........",
    "..........R...........",
]

# name -> (art rows, caption row, greeting)
_FESTIVALS: dict[str, tuple[list[str], int, str]] = {
    "DIWALI": (_DIWALI, 1, "HAPPY DIWALI"),
    "HOLI": (_HOLI, 2, "HAPPY HOLI"),
    "RAKHI": (_RAKHI, 1, "RAKSHA BANDHAN"),
    "GANESH": (_GANESH, 1, "GANESH CHATURTHI"),
    "DURGA": (_DURGA, 5, "DURGA PUJA"),
    "DUSSEHRA": (_DUSSEHRA, 5, "DUSSEHRA"),
    "NAVRATRI": (_NAVRATRI, 0, "HAPPY NAVRATRI"),
    "JANMASHTAMI": (_JANMASHTAMI, 0, "JANMASHTAMI"),
    "PONGAL": (_PONGAL, 0, "HAPPY PONGAL"),
    "ONAM": (_ONAM, 0, "HAPPY ONAM"),
    # Both Eids get the crescent; the greeting is the same either way.
    "EID_FITR": (_EID, 0, "EID MUBARAK"),
    "EID_ADHA": (_EID, 0, "EID MUBARAK"),
    "CHRISTMAS": (_CHRISTMAS, 0, "MERRY CHRISTMAS"),
}

# Dates from Google's public Indian-holidays iCal feed; see the module note.
_DATES: list[tuple[date, str]] = [
    (date(2026, 3, 4), "HOLI"),
    (date(2026, 8, 28), "RAKHI"),
    (date(2026, 9, 14), "GANESH"),
    (date(2026, 10, 17), "DURGA"),
    (date(2026, 10, 20), "DUSSEHRA"),
    (date(2026, 11, 8), "DIWALI"),
    (date(2027, 3, 22), "HOLI"),
    (date(2027, 8, 17), "RAKHI"),
    (date(2027, 9, 4), "GANESH"),
    (date(2027, 10, 5), "DURGA"),
    (date(2027, 10, 9), "DUSSEHRA"),
    (date(2027, 10, 29), "DIWALI"),
    (date(2028, 3, 11), "HOLI"),
    (date(2028, 8, 5), "RAKHI"),
    (date(2028, 8, 23), "GANESH"),
    (date(2028, 9, 24), "DURGA"),
    (date(2028, 9, 27), "DUSSEHRA"),
    (date(2028, 10, 17), "DIWALI"),
    (date(2029, 3, 1), "HOLI"),
    (date(2029, 8, 23), "RAKHI"),
    (date(2029, 9, 11), "GANESH"),
    (date(2029, 10, 12), "DURGA"),
    (date(2029, 10, 16), "DUSSEHRA"),
    (date(2029, 11, 5), "DIWALI"),
    (date(2030, 3, 20), "HOLI"),
    (date(2030, 8, 13), "RAKHI"),
    (date(2030, 9, 1), "GANESH"),
    (date(2030, 10, 2), "DURGA"),
    (date(2030, 10, 6), "DUSSEHRA"),
    (date(2030, 10, 26), "DIWALI"),
    (date(2031, 3, 9), "HOLI"),
    (date(2031, 8, 2), "RAKHI"),
    (date(2031, 9, 20), "GANESH"),
    (date(2031, 10, 21), "DURGA"),
    (date(2031, 10, 25), "DUSSEHRA"),
    (date(2031, 11, 14), "DIWALI"),
    (date(2026, 1, 14), "PONGAL"),
    (date(2026, 3, 21), "EID_FITR"),
    (date(2026, 5, 28), "EID_ADHA"),
    (date(2026, 8, 26), "ONAM"),
    (date(2026, 9, 4), "JANMASHTAMI"),
    (date(2026, 10, 11), "NAVRATRI"),
    (date(2026, 12, 25), "CHRISTMAS"),
    (date(2027, 1, 15), "PONGAL"),
    (date(2027, 3, 10), "EID_FITR"),
    (date(2027, 5, 17), "EID_ADHA"),
    (date(2027, 8, 25), "JANMASHTAMI"),
    (date(2027, 9, 12), "ONAM"),
    (date(2027, 9, 30), "NAVRATRI"),
    (date(2027, 12, 25), "CHRISTMAS"),
    (date(2028, 1, 15), "PONGAL"),
    (date(2028, 2, 27), "EID_FITR"),
    (date(2028, 5, 6), "EID_ADHA"),
    (date(2028, 8, 13), "JANMASHTAMI"),
    (date(2028, 9, 1), "ONAM"),
    (date(2028, 9, 19), "NAVRATRI"),
    (date(2028, 12, 25), "CHRISTMAS"),
    (date(2029, 1, 14), "PONGAL"),
    (date(2029, 2, 15), "EID_FITR"),
    (date(2029, 4, 25), "EID_ADHA"),
    (date(2029, 8, 22), "ONAM"),
    (date(2029, 9, 1), "JANMASHTAMI"),
    (date(2029, 10, 8), "NAVRATRI"),
    (date(2029, 12, 25), "CHRISTMAS"),
    (date(2030, 1, 14), "PONGAL"),
    (date(2030, 2, 5), "EID_FITR"),
    (date(2030, 4, 14), "EID_ADHA"),
    (date(2030, 8, 21), "JANMASHTAMI"),
    (date(2030, 9, 9), "ONAM"),
    (date(2030, 9, 28), "NAVRATRI"),
    (date(2030, 12, 25), "CHRISTMAS"),
    (date(2031, 1, 15), "PONGAL"),
    (date(2031, 1, 25), "EID_FITR"),
    (date(2031, 4, 3), "EID_ADHA"),
    (date(2031, 8, 10), "JANMASHTAMI"),
    (date(2031, 8, 30), "ONAM"),
    (date(2031, 10, 17), "NAVRATRI"),
    (date(2031, 12, 25), "CHRISTMAS"),
]

_BY_DATE: dict[date, str] = {when: name for when, name in _DATES}

LAST_KNOWN_YEAR = max(when.year for when, _ in _DATES)


def _today() -> date:
    # Wrapper so tests can pin the day — date is an immutable C type and
    # its .today() can't be patched in place. Same approach as f1/mufc.
    return date.today()


def build(name: str) -> list[int]:
    """The finished grid for one festival. Public so tests and any future
    'preview a festival' endpoint don't have to reach through run()."""
    rows, caption_row, greeting = _FESTIVALS[name]
    return caption(from_rows(rows), greeting, caption_row)


def run() -> ChannelMessage | None:
    today = _today()
    name = _BY_DATE.get(today)
    if name is None:
        return None

    # Expires at midnight: a festival greeting is for the day, and leaving
    # it in the rotation afterwards is how f1's countdown ended up owning
    # the board for a week.
    midnight = datetime.combine(today, time.max)

    return ChannelMessage(
        grid=build(name),
        priority=10,  # goes first among the day's new messages, but still rotates
        dwell_seconds=300,
        expires_at=midnight.timestamp(),
    )


# 07:30 — after quiet hours lift at 07:00, so the greeting is already up
# when the house comes downstairs.
CHANNEL = Channel(name="holiday", cron="30 7 * * *", run=run)
