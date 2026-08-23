"""
Horizontal + vertical placement (build plan §10 "Align"): centered both
axes by default. Odd leftover space biases top and left — floor division
on the padding does this automatically (the smaller gap lands first),
so don't "fix" it to round-half-up later; that would flip the bias.
"""
from __future__ import annotations

from .charset import BLANK_CODE, COLS, ROWS


def align(lines: list[list[int]], width: int = COLS) -> list[int]:
    """Centers up to ROWS lines (each already <= width codes) into one flat ROWS*width grid."""
    lines = lines[:ROWS]
    top_pad = (ROWS - len(lines)) // 2

    grid = [BLANK_CODE] * (ROWS * width)
    for i, line in enumerate(lines):
        row = top_pad + i
        left_pad = (width - len(line)) // 2
        start = row * width + left_pad
        grid[start : start + len(line)] = line
    return grid
