"""
Minimal text -> 6x22 grid conversion for Phase 2: uppercase, word-wrap
within COLS, center both axes, pad with blanks.

This is a placeholder for the real layout engine (Phase 3, build plan
§10) — normalize/wrap/align/templates as separate composable stages.
Don't grow this file; when Phase 3 lands, it replaces this wholesale.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
from charset import Charset  # noqa: E402

ROWS = 6
COLS = 22

_charset = Charset.load()
CHARSET_VERSION = _charset.version
BLANK_GRID = [_charset.blank_code] * (ROWS * COLS)


def _wrap(text: str) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        while len(word) > COLS:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:COLS])
            word = word[COLS:]
        candidate = f"{current} {word}".strip()
        if len(candidate) > COLS:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _normalize(text: str) -> str:
    # Illegal characters are dropped outright, not left as a gap — a
    # placeholder blank would misalign everything after it and read as a
    # rendering bug rather than "this character doesn't exist on the board."
    return "".join(ch for ch in text.upper() if _charset.code_for(ch) is not None)


def text_to_grid(text: str) -> list[int]:
    lines = _wrap(_normalize(text))[:ROWS]
    top_pad = (ROWS - len(lines)) // 2

    grid = list(BLANK_GRID)
    for i, line in enumerate(lines):
        row = top_pad + i
        left_pad = (COLS - len(line)) // 2
        for j, ch in enumerate(line):
            grid[row * COLS + left_pad + j] = _charset.code_for(ch)
    return grid
