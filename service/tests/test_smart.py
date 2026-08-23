from service.compose import CHARSET, COLS, ROWS
from service.compose.smart import pick


def _decode(grid: list[int]) -> str:
    rows = []
    for r in range(ROWS):
        row = grid[r * COLS : (r + 1) * COLS]
        rows.append("".join(CHARSET.char_for(c) or " " for c in row))
    return "\n".join(rows)


# --- countdown -----------------------------------------------------------


def test_countdown_number_unit_until_label():
    text = _decode(pick("5 days until vacation"))
    assert "5" in text
    assert "DAYS" in text
    assert "VACATION" in text


def test_countdown_label_in_number_unit():
    text = _decode(pick("trash pickup in 2 days"))
    assert "2" in text
    assert "DAYS" in text
    assert "TRASH PICKUP" in text


def test_countdown_only_matches_when_text_starts_with_the_number():
    # "Reminder: 5 days until vacation" doesn't start with a digit, so it
    # falls through to the colon/stat check instead of countdown.
    text = _decode(pick("Reminder: 5 days until vacation"))
    assert "REMINDER" in text
    assert "5 DAYS UNTIL VACATION" in text


# --- newline list ----------------------------------------------------------


def test_newline_separated_lines_become_a_list():
    text = _decode(pick("Groceries\nMilk\nEggs\nBread"))
    assert "GROCERIES" in text
    assert "MILK" in text
    assert "EGGS" in text
    assert "BREAD" in text


def test_single_line_is_not_treated_as_a_list():
    # No second line, so this falls through to the colon/stat check instead.
    grid = pick("just one line, no newline")
    assert grid is None  # no colon either, so nothing matches


# --- colon: stat vs list ----------------------------------------------------


def test_colon_with_two_comma_items_is_a_stat():
    text = _decode(pick("Outside: 72F, feels chilly"))
    assert "OUTSIDE" in text
    assert "72F" in text
    assert "FEELS CHILLY" in text


def test_colon_with_three_or_more_comma_items_is_a_list():
    text = _decode(pick("Groceries: milk, eggs, bread"))
    assert "GROCERIES" in text
    assert "MILK" in text
    assert "EGGS" in text
    assert "BREAD" in text


def test_colon_value_only_no_context_is_still_a_stat():
    text = _decode(pick("Status: OK"))
    assert "STATUS" in text
    assert "OK" in text


def test_overlong_label_before_colon_does_not_match():
    grid = pick("this label is way too long to be a real label: value")
    assert grid is None


# --- fallback ---------------------------------------------------------------


def test_plain_prose_falls_through_to_none():
    assert pick("just a normal sentence with no structure") is None


def test_blank_text_falls_through_to_none():
    assert pick("   ") is None


def test_every_match_is_a_valid_full_grid():
    for text in [
        "5 days until vacation",
        "trash pickup in 2 days",
        "Groceries\nMilk\nEggs",
        "Outside: 72F, feels chilly",
        "Groceries: milk, eggs, bread",
    ]:
        grid = pick(text)
        assert grid is not None
        assert len(grid) == ROWS * COLS
        for code in grid:
            assert 0 <= code < CHARSET.size
