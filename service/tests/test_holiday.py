from datetime import date, datetime

import pytest

from service.channels import holiday
from service.compose import CHARSET, COLS, ROWS
from service.compose.art import PALETTE


def _text(grid: list[int]) -> str:
    """Just the letters — chips read as spaces, like blanks."""
    rows = []
    for r in range(ROWS):
        row = grid[r * COLS : (r + 1) * COLS]
        rows.append("".join((CHARSET.char_for(c) or " ") for c in row))
    return "\n".join(rows)


def _chips(grid: list[int]) -> set[int]:
    return {c for c in grid if c in set(PALETTE.values()) and c != PALETTE["."]}


# --- the table ----------------------------------------------------------


def test_a_festival_day_posts_a_greeting(monkeypatch):
    monkeypatch.setattr(holiday, "_today", lambda: date(2026, 11, 8))  # Diwali
    assert "HAPPY DIWALI" in _text(holiday.run().grid)


def test_the_two_eids_share_art_and_greeting(monkeypatch):
    # Different dates, same crescent — the greeting doesn't distinguish them.
    monkeypatch.setattr(holiday, "_today", lambda: date(2026, 3, 21))  # Eid al-Fitr
    fitr = holiday.run().grid
    monkeypatch.setattr(holiday, "_today", lambda: date(2026, 5, 28))  # Eid al-Adha
    assert holiday.run().grid == fitr


def test_a_non_hindu_festival_is_greeted_too(monkeypatch):
    monkeypatch.setattr(holiday, "_today", lambda: date(2026, 12, 25))
    assert "MERRY CHRISTMAS" in _text(holiday.run().grid)


def test_an_ordinary_day_posts_nothing(monkeypatch):
    monkeypatch.setattr(holiday, "_today", lambda: date(2026, 11, 9))
    assert holiday.run() is None


def test_every_festival_in_the_table_can_actually_be_built():
    # A date whose name has no art would raise KeyError at 7:30am on the
    # one morning it matters, so check the whole table up front.
    for when, name in holiday._DATES:
        assert name in holiday._FESTIVALS, f"{when} refers to unknown festival {name!r}"
        holiday.build(name)


def test_every_festival_is_covered_every_year():
    by_year: dict[int, set[str]] = {}
    for when, name in holiday._DATES:
        by_year.setdefault(when.year, set()).add(name)
    for year, names in by_year.items():
        assert names == set(holiday._FESTIVALS), f"{year} is missing {set(holiday._FESTIVALS) - names}"


def test_no_two_festivals_land_on_the_same_day():
    days = [when for when, _ in holiday._DATES]
    assert len(days) == len(set(days))


def test_the_table_has_not_silently_run_out():
    # Not a date assertion — a reminder. When this fails, regenerate from
    # the iCal feed named in the module docstring.
    assert holiday.LAST_KNOWN_YEAR >= 2031


# --- the art ------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(holiday._FESTIVALS))
def test_each_festival_is_a_valid_full_grid(name):
    grid = holiday.build(name)
    assert len(grid) == ROWS * COLS
    for code in grid:
        assert 0 <= code < CHARSET.size


@pytest.mark.parametrize("name", sorted(holiday._FESTIVALS))
def test_each_festival_has_both_art_and_a_greeting(name):
    grid = holiday.build(name)
    assert _chips(grid), f"{name} has no colour in it"
    assert _text(grid).strip(), f"{name} has no readable greeting"


def test_the_caption_row_is_not_buried_under_art():
    # caption() clears its row before writing, so the greeting is always on
    # unlit cells however busy the art around it gets.
    rows, caption_row, _ = holiday._FESTIVALS["HOLI"]
    grid = holiday.build("HOLI")
    start = caption_row * COLS
    for code in grid[start : start + COLS]:
        assert code not in _chips(grid) or code == PALETTE["."]


def test_diwali_uses_flame_colours_not_arbitrary_ones():
    grid = holiday.build("DIWALI")
    assert _chips(grid) == {PALETTE["Y"], PALETTE["O"], PALETTE["R"]}


def test_holi_uses_many_colours_because_that_is_the_point():
    assert len(_chips(holiday.build("HOLI"))) >= 5


# --- posting ------------------------------------------------------------


def test_the_greeting_expires_at_the_end_of_the_day(monkeypatch):
    monkeypatch.setattr(holiday, "_today", lambda: date(2026, 11, 8))
    message = holiday.run()
    expires = datetime.fromtimestamp(message.expires_at)
    assert expires.date() == date(2026, 11, 8)
    assert (expires.hour, expires.minute) == (23, 59)


def test_posted_as_a_grid_so_the_art_survives(monkeypatch):
    monkeypatch.setattr(holiday, "_today", lambda: date(2026, 3, 4))  # Holi
    message = holiday.run()
    # text= would go through the layout engine and the colours would be lost.
    assert message.text is None
    assert message.grid is not None


def test_channel_runs_after_quiet_hours_lift():
    assert holiday.CHANNEL.name == "holiday"
    assert holiday.CHANNEL.cron == "30 7 * * *"  # 07:30, quiet hours end at 07:00
