"""
Text -> legal flap codes (build plan §10 "Normalize"):
uppercase; apply spec transliterations (handled by Charset.code_for);
emoji -> nearest color chip where one maps, else drop; anything still
illegal is dropped, never a placeholder box.

Output is a flat list of codes plus two internal sentinels consumed only
by wrap.py — they never reach a final grid:
  NEWLINE  an explicit \\n the author typed, forces a hard line break
  (blanks collapse naturally: runs of whitespace produce a single
  CHARSET.blank_code, so wrap.py never sees repeats)
"""
from __future__ import annotations

from .charset import CHARSET

NEWLINE = -1

# The charset has 7 color chips and no per-color lookup by name — this is
# the one place that maps a hex color to "which chip code is that."
_CHIP_CODE_BY_COLOR: dict[str, int] = {
    d.color: d.code for d in CHARSET.flaps if d.type == "chip" and d.color
}

_CHIP_HEX_BY_NAME = {
    "red": "#C0392B",
    "orange": "#E67E22",
    "yellow": "#F1C40F",
    "green": "#27AE60",
    "blue": "#2980B9",
    "violet": "#8E44AD",
    "white": "#ECF0F1",
}

# U+FE0F, the emoji variation selector. Phones append it to characters
# that have both a text and an emoji presentation, so "❤️" arrives as two
# codepoints (U+2764 U+FE0F). normalize() iterates codepoints, so a
# two-codepoint key here could never match and the chip was silently
# dropped instead — keys below must stay single-codepoint, which
# test_emoji_table_keys_are_single_codepoints enforces.
_VARIATION_SELECTOR = "\ufe0f"

# A small, explicit emoji -> chip-color-name table. Extend as needed;
# anything not listed here just falls through to "illegal, dropped."
_EMOJI_TO_COLOR_NAME = {
    "🔴": "red",
    "❤": "red",
    "🟠": "orange",
    "🟡": "yellow",
    "💛": "yellow",
    "🟢": "green",
    "✅": "green",
    "🔵": "blue",
    "💙": "blue",
    "🟣": "violet",
    "💜": "violet",
    "⚪": "white",
}


def _chip_code_for_emoji(ch: str) -> int | None:
    name = _EMOJI_TO_COLOR_NAME.get(ch)
    if name is None:
        return None
    return _CHIP_CODE_BY_COLOR.get(_CHIP_HEX_BY_NAME[name])


def normalize(text: str) -> list[int]:
    codes: list[int] = []
    pending_blank = False  # a collapsed whitespace run, emitted lazily so
    # trailing spaces before a newline or end-of-string never leave a
    # dangling blank code with nothing after it.

    for ch in text.strip():
        if ch == _VARIATION_SELECTOR:
            continue  # a presentation hint, not a character — never its own cell
        if ch == "\n":
            codes.append(NEWLINE)
            pending_blank = False
            continue
        if ch.isspace():
            pending_blank = True
            continue

        code = CHARSET.code_for(ch.upper())
        if code is None:
            code = _chip_code_for_emoji(ch)
        if code is None:
            continue  # illegal — dropped outright, never a placeholder

        if pending_blank:
            codes.append(CHARSET.blank_code)
            pending_blank = False
        codes.append(code)

    return codes
