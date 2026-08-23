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

from .templates import countdown, list_template, stat

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
_MAX_LABEL_LEN = 20


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
        return countdown(m["label"], m["number"], m["unit"])

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) >= 2:
        return list_template(lines[0], lines[1:])

    colon = _colon_split(text)
    if colon:
        label, rest = colon
        items = [i.strip() for i in rest.split(",") if i.strip()]
        if len(items) >= _LIST_MIN_ITEMS:
            return list_template(label, items)
        value, _, context = rest.partition(",")
        return stat(label, value.strip(), context.strip())

    return None
