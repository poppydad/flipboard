"""
Chip art: drawing pictures on the board with the seven colour flaps.

The board is 6 rows of 22 cells and each cell is one flat colour, so this
is closer to cross-stitch than to drawing. What works is a silhouette read
at a distance — a row of lamps, a scatter of colour, a trident — not
detail. What doesn't work is anything needing more than about three
colours in one shape, or a curve narrower than a whole cell.

Art is written as literal rows of single-character keys, so the source
looks like the thing it renders:

    diya = from_rows([
        "......................",
        ".........YY...........",
        ...
    ])

That legibility is the point. A grid built by index arithmetic is
unreviewable — you cannot tell a correct one from a broken one by reading
it, and neither can the next person.

Colour choice belongs to the caller (a channel), not here; this module
only knows how to turn characters into cells and how to put a line of
text on top of them.
"""
from __future__ import annotations

from .charset import BLANK_CODE, COLS, ROWS
from .normalize import _CHIP_CODE_BY_COLOR, _CHIP_HEX_BY_NAME, normalize
from .wrap import wrap

# One letter per colour, plus "." for an unlit cell. Single characters so a
# row of art is exactly as wide as the board it describes.
PALETTE: dict[str, int] = {
    ".": BLANK_CODE,
    "R": _CHIP_CODE_BY_COLOR[_CHIP_HEX_BY_NAME["red"]],
    "O": _CHIP_CODE_BY_COLOR[_CHIP_HEX_BY_NAME["orange"]],
    "Y": _CHIP_CODE_BY_COLOR[_CHIP_HEX_BY_NAME["yellow"]],
    "G": _CHIP_CODE_BY_COLOR[_CHIP_HEX_BY_NAME["green"]],
    "B": _CHIP_CODE_BY_COLOR[_CHIP_HEX_BY_NAME["blue"]],
    "V": _CHIP_CODE_BY_COLOR[_CHIP_HEX_BY_NAME["violet"]],
    "W": _CHIP_CODE_BY_COLOR[_CHIP_HEX_BY_NAME["white"]],
}


def from_rows(rows: list[str]) -> list[int]:
    """Rows of palette keys to a flat ROWS*COLS grid.

    Strict about shape on purpose: art is written by hand, and a row one
    character short would otherwise shift everything below it sideways and
    look like a rendering bug rather than a typo.
    """
    if len(rows) != ROWS:
        raise ValueError(f"art needs exactly {ROWS} rows, got {len(rows)}")

    grid: list[int] = []
    for i, row in enumerate(rows):
        if len(row) != COLS:
            raise ValueError(f"row {i} is {len(row)} cells wide, expected {COLS}: {row!r}")
        for j, key in enumerate(row):
            try:
                grid.append(PALETTE[key])
            except KeyError:
                raise ValueError(
                    f"unknown palette key {key!r} at row {i} col {j}; "
                    f"expected one of {''.join(sorted(PALETTE))}"
                ) from None
    return grid


def caption(grid: list[int], text: str, row: int) -> list[int]:
    """Centre one line of text onto `row` of an existing grid.

    Overwrites the whole row rather than compositing over it, so a caption
    always sits on unlit cells and stays readable regardless of what the
    art was doing underneath. Text too long for one row is truncated — the
    caller controls the wording here, unlike POST /message, and silently
    reflowing a greeting into art rows would be worse than clipping it.
    """
    if not 0 <= row < ROWS:
        raise ValueError(f"row {row} is outside 0..{ROWS - 1}")

    lines = wrap(normalize(text), width=COLS)
    line = lines[0] if lines else []

    out = list(grid)
    start = row * COLS
    out[start : start + COLS] = [BLANK_CODE] * COLS
    left = (COLS - len(line)) // 2
    out[start + left : start + left + len(line)] = line
    return out
