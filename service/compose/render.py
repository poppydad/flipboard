"""
Orchestrates normalize -> wrap -> align into one or more flat ROWS*COLS
grids. Content over ROWS lines never truncates silently (build plan
§10) — it splits into sequential pages instead. The caller (service/main.py)
is what turns multiple pages into linked messages with shorter dwell;
this module just refuses to drop content.
"""
from __future__ import annotations

from .align import align
from .charset import BLANK_GRID, CHARSET, COLS, ROWS
from .normalize import normalize
from .wrap import wrap


def render(text: str) -> list[list[int]]:
    """Returns one or more flat ROWS*COLS grids — normally one page, more if it overflows."""
    lines = wrap(normalize(text))
    if not lines or lines == [[]]:
        return [list(BLANK_GRID)]

    pages = [lines[i : i + ROWS] for i in range(0, len(lines), ROWS)]
    return [align(page) for page in pages]


def decode(grid: list[int]) -> str:
    """Grid back to readable text — the rough inverse of render().

    Lossy on purpose: it exists so a person can recognise a message in a
    list, not to round-trip. Blank rows are dropped and remaining rows are
    joined with " / ", so a `stat` grid reads "WEATHER / 75F / OVERCAST".
    Colour chips have no character form and come back as spaces, so a
    grid that's purely a chip pattern decodes to "" — callers should fall
    back to something like "(pattern)" rather than showing nothing.
    """
    rows = []
    for r in range(ROWS):
        row = "".join(CHARSET.char_for(c) or " " for c in grid[r * COLS : (r + 1) * COLS])
        if row.strip():
            rows.append(" ".join(row.split()))
    return " / ".join(rows)
