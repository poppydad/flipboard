"""
Orchestrates normalize -> wrap -> align into one or more flat ROWS*COLS
grids. Content over ROWS lines never truncates silently (build plan
§10) — it splits into sequential pages instead. The caller (service/main.py)
is what turns multiple pages into linked messages with shorter dwell;
this module just refuses to drop content.
"""
from __future__ import annotations

from .align import align
from .charset import BLANK_GRID, ROWS
from .normalize import normalize
from .wrap import wrap


def render(text: str) -> list[list[int]]:
    """Returns one or more flat ROWS*COLS grids — normally one page, more if it overflows."""
    lines = wrap(normalize(text))
    if not lines or lines == [[]]:
        return [list(BLANK_GRID)]

    pages = [lines[i : i + ROWS] for i in range(0, len(lines), ROWS)]
    return [align(page) for page in pages]
