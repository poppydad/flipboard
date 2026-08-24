"""
Free stand-in for the Claude-composition slot in build plan §11
("`POST /compose/smart`... only if probe 7 was green" — probe 7, a paid
API call, was never run). Instead of asking an LLM to decide *what to
say and how to shape it*, this recognizes a handful of common text
shapes by regex and maps them straight onto the existing templates:

    "5 days until vacation"        -> countdown(label="VACATION", number="5", unit="DAYS")
    "trash pickup in 2 days"       -> countdown(label="TRASH PICKUP", number="2", unit="DAYS")
    "Outside: 72F, feels chilly"   -> stat(label="OUTSIDE", value="72F", context="FEELS CHILLY")
    "Groceries: milk, eggs, bread" -> list_template("GROCERIES", ["milk", "eggs", "bread"])
    "Groceries\\nMilk\\nEggs"      -> list_template("Groceries", ["Milk", "Eggs"])
    anything else                  -> None (caller falls back to plain render())

Deliberately narrow and honest about it: no attempt to parse intent out
of free-form prose. `pick()` returning `None` is not a failure mode, it's
the expected outcome for most input — the caller's fallback (the same
render() path POST /message already uses) handles that case, matching
the "fall back to banner on anything malformed" instruction in §11.
"""
from __future__ import annotations

import re

from .charset import COLS
from .normalize import normalize
from .templates import countdown, list_template, stat
from .wrap import wrap

_COUNTDOWN_UNTIL_RE = re.compile(
    r"^(?P<number>\d+)\s+(?P<unit>days?|hours?|weeks?)\s+(?:until|till|to)\s+(?P<label>.+)$",
    re.IGNORECASE,
)
_COUNTDOWN_IN_RE = re.compile(
    r"^(?P<label>.+?)\s+in\s+(?P<number>\d+)\s+(?P<unit>days?|hours?|weeks?)$",
    re.IGNORECASE,
)

# List items need >= this many comma-separated values before "label: a, b"
# is read as a list rather than a stat's "value, context" (2 items).
_LIST_MIN_ITEMS = 3
# templates.list_template places items on fixed rows and slices to [:4].
_MAX_LIST_ITEMS = 4
_MAX_LABEL_LEN = 20


def _fits(text: str) -> bool:
    """True if `text` occupies at most one line of COLS codes.

    Templates put each field on a fixed row via templates._one_line,
    which keeps `lines[0]` and drops the rest — fine for the short
    structured values channels feed it, but smart.pick() feeds it
    arbitrary text a person typed. Anything that would wrap has to fall
    through to render() instead, which paginates rather than truncating
    (build plan §10: "never truncate silently"). Without this check
    "Reminder: pick up the dry cleaning before six today" rendered as
    "REMINDER / PICK UP THE DRY" and lost the rest.
    """
    if not text:
        return True  # an omitted stat context is legal, not an overflow
    return len(wrap(normalize(text), width=COLS)) <= 1


def _colon_split(text: str) -> tuple[str, str] | None:
    if ":" not in text:
        return None
    label, _, rest = text.partition(":")
    label, rest = label.strip(), rest.strip()
    if not label or not rest or len(label) > _MAX_LABEL_LEN:
        return None
    return label, rest


def pick(text: str) -> list[int] | None:
    """Returns a built grid if `text` matches a recognized shape, else None."""
    text = text.strip()
    if not text:
        return None

    m = _COUNTDOWN_UNTIL_RE.match(text) or _COUNTDOWN_IN_RE.match(text)
    if m:
        fields = (m["label"], m["number"], m["unit"])
        if not all(_fits(f) for f in fields):
            return None
        return countdown(*fields)

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) >= 2:
        return _list_or_none(lines[0], lines[1:])

    colon = _colon_split(text)
    if colon:
        label, rest = colon
        items = [i.strip() for i in rest.split(",") if i.strip()]
        if len(items) >= _LIST_MIN_ITEMS:
            return _list_or_none(label, items)
        value, _, context = rest.partition(",")
        value, context = value.strip(), context.strip()
        if not all(_fits(f) for f in (label, value, context)):
            return None
        return stat(label, value, context)

    return None


def _list_or_none(header: str, items: list[str]) -> list[int] | None:
    """A list only survives if every line fits and nothing would be
    dropped by list_template's items[:4] slice."""
    if len(items) > _MAX_LIST_ITEMS:
        return None
    if not _fits(header) or not all(_fits(i) for i in items):
        return None
    return list_template(header, items)
