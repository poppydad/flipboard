"""Tests for service/compose/ per build plan §10's explicit test list."""
from service.compose import CHARSET, COLS, ROWS, align, decode as _decode_text, normalize, render, wrap
from service.compose.normalize import NEWLINE
from service.compose.templates import TEMPLATES, banner, chips, countdown, list_template, stat


def _decode(grid: list[int]) -> list[str]:
    rows = []
    for r in range(ROWS):
        row = grid[r * COLS : (r + 1) * COLS]
        rows.append("".join(CHARSET.char_for(c) or " " for c in row))
    return rows


# --- normalize ---------------------------------------------------------


def test_every_legal_code_round_trips():
    for defn in CHARSET.flaps:
        if defn.char is None or defn.char == " ":
            continue  # chips have no char form; blank round-trips trivially
        assert normalize(defn.char) == [defn.code]


def test_illegal_character_drops_not_placeholder():
    # '@' vanishes entirely — no gap, no placeholder — collapsing "A@B" to "AB".
    assert normalize("A@B") == [CHARSET.code_for("A"), CHARSET.code_for("B")]


def test_whitespace_run_collapses_to_one_blank():
    assert normalize("A    B") == [CHARSET.code_for("A"), CHARSET.blank_code, CHARSET.code_for("B")]


def test_explicit_newline_becomes_sentinel_not_dropped():
    assert normalize("A\nB") == [CHARSET.code_for("A"), NEWLINE, CHARSET.code_for("B")]


def test_leading_and_trailing_whitespace_stripped():
    assert normalize("  A  ") == [CHARSET.code_for("A")]


def test_emoji_resolves_to_matching_chip():
    red_code = next(f.code for f in CHARSET.flaps if f.type == "chip" and f.color == "#C0392B")
    assert normalize("🔴")[0] == red_code


def test_unmapped_emoji_drops_like_any_illegal_char():
    assert normalize("A🚀B") == [CHARSET.code_for("A"), CHARSET.code_for("B")]


# --- wrap ----------------------------------------------------------------


def test_word_exactly_cols_long_fits_one_line_no_wrap():
    word = list(range(1, COLS + 1))  # 22 arbitrary non-blank codes
    lines = wrap(word)
    assert len(lines) == 1
    assert lines[0] == word


def test_word_one_longer_than_cols_hard_breaks_no_hyphen():
    word = [CHARSET.code_for("X")] * (COLS + 1)
    lines = wrap(word)
    assert len(lines) == 2
    assert lines[0] == [CHARSET.code_for("X")] * COLS
    assert lines[1] == [CHARSET.code_for("X")]
    hyphen = CHARSET.code_for("-")
    assert hyphen not in lines[0] and hyphen not in lines[1]


def test_never_breaks_mid_word_under_col_limit():
    codes = normalize("ONE TWO THREEFOURFIVE")
    lines = wrap(codes)
    flat_words = [_decode_line(line) for line in lines]
    assert any("THREEFOURFIVE" in line for line in flat_words)


def test_explicit_newline_forces_a_break_even_mid_capacity():
    codes = normalize("A\nB")
    lines = wrap(codes)
    assert len(lines) == 2


def test_double_newline_produces_a_blank_line():
    codes = normalize("A\n\nB")
    lines = wrap(codes)
    assert len(lines) == 3
    assert lines[1] == []


def _decode_line(line: list[int]) -> str:
    return "".join(CHARSET.char_for(c) or " " for c in line)


# --- align ---------------------------------------------------------------


def test_align_centers_single_line_both_axes():
    line = normalize("HI")
    grid = align([line])
    rows = _decode(grid)
    assert rows[2] == " " * 10 + "HI" + " " * 10


def test_align_odd_leftover_biases_top_and_left():
    # 3 lines into 6 rows: leftover 3, top_pad = 3//2 = 1 -> smaller gap on top.
    lines = [normalize("A"), normalize("B"), normalize("C")]
    grid = align(lines)
    rows = _decode(grid)
    assert rows[1].strip() == "A"  # top gap is 1 row, not 2
    # 1-char line into 22 cols: leftover 21, left_pad = 21//2 = 10 -> smaller gap on left.
    assert rows[1] == " " * 10 + "A" + " " * 11


# --- render (orchestration + pagination) ----------------------------------


def test_empty_string_is_a_blank_grid_not_a_crash():
    pages = render("")
    assert len(pages) == 1
    assert all(c == CHARSET.blank_code for c in pages[0])


def test_content_over_rows_paginates_with_zero_lost_words():
    words = [f"W{i}" for i in range(150)]  # forces many lines, well over ROWS
    text = " ".join(words)
    assert len(text) > 500

    pages = render(text)
    assert len(pages) > 1

    seen_words: list[str] = []
    for page in pages:
        for row in _decode(page):
            seen_words.extend(row.split())
    assert seen_words == words  # every word present, in order, none dropped


def test_single_page_when_content_fits():
    assert len(render("HELLO WORLD")) == 1


# --- templates -------------------------------------------------------------


def _assert_valid_grid(grid: list[int]) -> None:
    assert len(grid) == ROWS * COLS
    for code in grid:
        assert 0 <= code < CHARSET.size  # Charset.load() guarantees 0..size-1 is contiguous
        CHARSET.char_for(code)  # raises IndexError on an out-of-range code


def test_every_template_output_is_exactly_6x22_with_legal_codes():
    _assert_valid_grid(banner("HELLO"))
    _assert_valid_grid(stat("LABEL", "VALUE", "CONTEXT"))
    _assert_valid_grid(list_template("HEADER", ["A", "B", "C", "D"]))
    _assert_valid_grid(countdown("LABEL", "3", "DAYS"))
    _assert_valid_grid(chips("FRAMED", "red"))


def test_templates_registry_matches_the_five_named_layouts():
    assert set(TEMPLATES) == {"banner", "stat", "list", "countdown", "chips"}


def test_chips_unknown_color_raises():
    import pytest

    with pytest.raises(ValueError):
        chips("TEXT", "not-a-color")


def test_chips_border_columns_are_solid_chip_code():
    red_code = next(f.code for f in CHARSET.flaps if f.type == "chip" and f.color == "#C0392B")
    grid = chips("X", "red")
    for r in range(ROWS):
        assert grid[r * COLS] == red_code
        assert grid[r * COLS + COLS - 1] == red_code


def test_emoji_with_variation_selector_still_resolves_to_a_chip():
    """Phones send "❤️" as U+2764 U+FE0F. normalize() iterates codepoints,
    so the trailing selector must be skipped rather than dropping the chip."""
    red = next(f.code for f in CHARSET.flaps if f.type == "chip" and f.color == "#C0392B")
    assert normalize("❤️") == [red]
    assert normalize("A❤️B") == [CHARSET.code_for("A"), red, CHARSET.code_for("B")]


def test_emoji_table_keys_are_single_codepoints():
    """A multi-codepoint key can never match, because normalize() walks the
    string one codepoint at a time — it would be silently dead."""
    from service.compose.normalize import _EMOJI_TO_COLOR_NAME

    for emoji in _EMOJI_TO_COLOR_NAME:
        assert len(emoji) == 1, f"{emoji!r} is {len(emoji)} codepoints and can never match"


# --- decode (grid -> readable text, for the queue list) ------------------


def test_decode_drops_blank_rows_and_joins_with_slashes():
    assert _decode_text(stat("WEATHER", "75F", "OVERCAST")) == "WEATHER / 75F / OVERCAST"


def test_decode_collapses_the_centering_padding():
    # banner() centers, so the row is mostly blanks — none of which should
    # survive into a preview shown in a list.
    assert _decode_text(banner("HELLO")) == "HELLO"


def test_decode_of_a_blank_grid_is_empty():
    from service.compose import BLANK_GRID

    assert _decode_text(list(BLANK_GRID)) == ""


def test_decode_of_a_pure_chip_pattern_is_empty_not_garbage():
    # Chips have no character form. Callers show "(pattern)" for this.
    red = next(f.code for f in CHARSET.flaps if f.type == "chip" and f.color == "#C0392B")
    assert _decode_text([red] * (ROWS * COLS)) == ""
