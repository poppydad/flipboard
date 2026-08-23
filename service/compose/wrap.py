"""
Word-wraps a flat code stream into lines of at most COLS codes (build
plan §10 "Wrap"): never break mid-word unless the word exceeds COLS
(then hard-break, no hyphen); honor explicit NEWLINE (from normalize.py)
as a forced break. Whitespace-run collapsing already happened in
normalize.py, so this only ever sees single blank codes as separators.

Operates on codes, not characters — a color chip wraps exactly like a
letter, which is what you want (it's one cell, same as any glyph).
"""
from __future__ import annotations

from .charset import BLANK_CODE, COLS
from .normalize import NEWLINE


def wrap(codes: list[int], width: int = COLS) -> list[list[int]]:
    lines: list[list[int]] = []
    current: list[int] = []
    word: list[int] = []

    def flush_word() -> None:
        nonlocal current, word
        if not word:
            return
        while len(word) > width:
            if current:
                lines.append(current)
                current = []
            lines.append(word[:width])
            word = word[width:]
        needs_space = 1 if current else 0
        if len(current) + needs_space + len(word) > width:
            lines.append(current)
            current = word[:]
        else:
            current = current + ([BLANK_CODE] if current else []) + word
        word = []

    def flush_line() -> None:
        nonlocal current
        flush_word()
        lines.append(current)
        current = []

    for code in codes:
        if code == NEWLINE:
            flush_line()
        elif code == BLANK_CODE:
            flush_word()
        else:
            word.append(code)

    flush_word()
    if current or not lines:
        lines.append(current)
    return lines
