import json
import sqlite3

import pytest

from service.compose import BLANK_GRID, CHARSET, COLS, ROWS
from service.db import SCHEMA
from service.messages import create_message, validate_grid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.commit()
    yield c
    c.close()


def test_text_creates_one_row_for_short_content(conn):
    ids = create_message(conn, source="manual", text="HELLO")
    assert len(ids) == 1
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (ids[0],)).fetchone()
    assert row["source"] == "manual"
    assert row["raw_text"] == "HELLO"
    assert len(json.loads(row["grid"])) == ROWS * COLS


def test_text_overflow_creates_one_row_per_page_with_split_dwell(conn):
    long_text = " ".join(f"W{i}" for i in range(150))
    ids = create_message(conn, source="manual", text=long_text, dwell_seconds=100)
    assert len(ids) > 1

    rows = [conn.execute("SELECT * FROM messages WHERE id = ?", (i,)).fetchone() for i in ids]
    assert all(r["raw_text"] == long_text for r in rows)  # full text kept on every page
    assert all(r["dwell_seconds"] == max(20, 100 // len(ids)) for r in rows)


def test_dwell_floor_applies_when_pages_would_flash_too_fast(conn):
    long_text = " ".join(f"W{i}" for i in range(150))
    ids = create_message(conn, source="manual", text=long_text, dwell_seconds=10)
    rows = [conn.execute("SELECT * FROM messages WHERE id = ?", (i,)).fetchone() for i in ids]
    assert all(r["dwell_seconds"] == 20 for r in rows)  # 10 // N < floor, so floor wins


def test_grid_input_is_a_single_page_never_paginated(conn):
    grid = list(BLANK_GRID)
    ids = create_message(conn, source="weather", grid=grid, dwell_seconds=60)
    assert len(ids) == 1
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (ids[0],)).fetchone()
    assert row["raw_text"] is None
    assert json.loads(row["grid"]) == grid
    assert row["dwell_seconds"] == 60


def test_neither_text_nor_grid_raises(conn):
    with pytest.raises(ValueError):
        create_message(conn, source="manual")


def test_both_text_and_grid_raises(conn):
    with pytest.raises(ValueError):
        create_message(conn, source="manual", text="X", grid=list(BLANK_GRID))


def test_validate_grid_accepts_a_well_formed_grid():
    validate_grid(list(BLANK_GRID))  # no raise


def test_validate_grid_rejects_wrong_length():
    with pytest.raises(ValueError):
        validate_grid([0] * (ROWS * COLS - 1))


def test_validate_grid_rejects_out_of_range_codes():
    grid = list(BLANK_GRID)
    grid[0] = CHARSET.size  # one past the last valid code
    with pytest.raises(ValueError):
        validate_grid(grid)


def test_validate_grid_rejects_negative_codes():
    grid = list(BLANK_GRID)
    grid[0] = -1
    with pytest.raises(ValueError):
        validate_grid(grid)


def test_grid_message_posts_a_full_page_of_color_chips(conn):
    chip_code = next(f.code for f in CHARSET.flaps if f.type == "chip")
    grid = [chip_code] * (ROWS * COLS)
    validate_grid(grid)  # the boundary check a POST /message/grid request goes through
    ids = create_message(conn, source="manual", grid=grid, dwell_seconds=120)
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (ids[0],)).fetchone()
    assert json.loads(row["grid"]) == grid
