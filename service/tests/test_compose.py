from service.compose import COLS, ROWS, text_to_grid
from python.charset import Charset  # noqa: E402  (compose.py puts python/ on sys.path)

charset = Charset.load()


def _decode(grid: list[int]) -> list[str]:
    """Grid -> list of ROWS strings, blanks as spaces, for readable assertions."""
    rows = []
    for r in range(ROWS):
        row = grid[r * COLS : (r + 1) * COLS]
        rows.append("".join(charset.char_for(c) or " " for c in row))
    return rows


def test_short_word_centered_both_axes():
    rows = _decode(text_to_grid("HI"))
    assert rows[2] == " " * 10 + "HI" + " " * 10  # row (6-1)//2 = 2, col (22-2)//2 = 10
    assert rows[0].strip() == "" and rows[5].strip() == ""


def test_wrap_never_breaks_mid_word_under_col_limit():
    text = "ONE TWO THREEFOURFIVE"  # third word alone is 13 chars, fits on one line
    rows = _decode(text_to_grid(text))
    joined = "\n".join(rows)
    assert "ONE TWO" in joined
    assert "THREEFOURFIVE" in joined


def test_word_longer_than_cols_hard_breaks_no_hyphen():
    long_word = "X" * 30  # breaks into a full 22-char line + an 8-char line, 2 lines total
    grid = text_to_grid(long_word)
    rows = _decode(grid)
    top_pad = (ROWS - 2) // 2
    # A line that exactly fills COLS has zero left_pad, so it's flush X's, no centering.
    assert rows[top_pad] == "X" * COLS
    assert "X" * 8 in rows[top_pad + 1]
    assert "-" not in "".join(rows)  # no hyphen ever inserted


def test_empty_string_is_a_blank_grid_not_a_crash():
    grid = text_to_grid("")
    assert all(c == charset.blank_code for c in grid)


def test_unknown_character_drops_rather_than_placeholder():
    grid = text_to_grid("A@B")  # the @ sign has no charset entry
    rows = _decode(grid)
    assert "AB" in "".join(rows)  # collapsed together, not "A?B" or similar
