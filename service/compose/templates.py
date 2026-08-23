"""
Named layouts (build plan §10 "Templates"): structured field input -> one
flat ROWS*COLS grid, using fixed row positions rather than paragraph
flow. Each field is one wrapped/centered line, not word-wrapped across
the whole template — these are for short structured values (a weather
stat, a countdown), not prose.
"""
from __future__ import annotations

from .align import align
from .charset import BLANK_GRID, COLS, ROWS
from .normalize import _CHIP_CODE_BY_COLOR, _CHIP_HEX_BY_NAME, normalize
from .wrap import wrap


def _one_line(text: str) -> list[int]:
    lines = wrap(normalize(text))
    return lines[0] if lines else []


def _place(rows: list[list[int]]) -> list[int]:
    """Places up to ROWS pre-built lines (each already <= COLS codes) at
    their literal row index, horizontally centered — no vertical
    centering, unlike align(); the caller already chose the spacing."""
    grid = list(BLANK_GRID)
    for r, line in enumerate(rows[:ROWS]):
        left_pad = (COLS - len(line)) // 2
        start = r * COLS + left_pad
        grid[start : start + len(line)] = line
    return grid


def banner(text: str) -> list[int]:
    """One line, centered — the board's single biggest statement."""
    return align([_one_line(text)])


def stat(label: str, value: str, context: str = "") -> list[int]:
    """label / value / context, evenly spaced top to bottom."""
    return _place([[], _one_line(label), [], _one_line(value), [], _one_line(context)])


def list_template(header: str, items: list[str]) -> list[int]:
    """header + up to 4 items, top-aligned with a blank row at the bottom."""
    return _place([_one_line(header)] + [_one_line(item) for item in items[:4]])


def countdown(label: str, number: str, unit: str) -> list[int]:
    """label / number / unit — same spacing as stat, different semantics."""
    return _place([[], _one_line(label), [], _one_line(number), [], _one_line(unit)])


def chips(text: str, color: str) -> list[int]:
    """A solid chip-colored border (1 column each side) framing centered text."""
    if color not in _CHIP_HEX_BY_NAME:
        raise ValueError(f"unknown chip color {color!r}, expected one of {sorted(_CHIP_HEX_BY_NAME)}")
    chip_code = _CHIP_CODE_BY_COLOR[_CHIP_HEX_BY_NAME[color]]

    inner_width = COLS - 2
    inner = align(wrap(normalize(text), width=inner_width), width=inner_width)

    grid = [chip_code] * (ROWS * COLS)
    for r in range(ROWS):
        src = r * inner_width
        dst = r * COLS + 1
        grid[dst : dst + inner_width] = inner[src : src + inner_width]
    return grid


TEMPLATES = {
    "banner": banner,
    "stat": stat,
    "list": list_template,
    "countdown": countdown,
    "chips": chips,
}
