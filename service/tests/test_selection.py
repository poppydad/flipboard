import sqlite3

import pytest

from service.db import SCHEMA
from service.selection import Selector


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.commit()
    yield c
    c.close()


def insert(conn, *, priority=50, dwell_seconds=300, pinned=False, starts_at=None, expires_at=None, text="X"):
    cur = conn.execute(
        "INSERT INTO messages (source, raw_text, grid, priority, dwell_seconds, starts_at, expires_at, pinned) "
        "VALUES ('manual', ?, '[]', ?, ?, ?, ?, ?)",
        (text, priority, dwell_seconds, starts_at, expires_at, int(pinned)),
    )
    conn.commit()
    return cur.lastrowid


def test_picks_lowest_priority_number(conn):
    low_prio_wins = insert(conn, priority=10)
    insert(conn, priority=50)
    selector = Selector()
    row = selector.current(conn)
    assert row["id"] == low_prio_wins


def test_pinned_beats_lower_priority_number(conn):
    insert(conn, priority=0)  # would win on priority alone
    pinned_id = insert(conn, priority=99, pinned=True)
    selector = Selector()
    row = selector.current(conn)
    assert row["id"] == pinned_id


def test_ties_broken_by_least_recently_shown(conn):
    a = insert(conn, priority=10, dwell_seconds=0)
    b = insert(conn, priority=10, dwell_seconds=0)
    selector = Selector()

    first = selector.current(conn)
    # dwell_seconds=0 means the very next call reselects immediately.
    second = selector.current(conn, force=True)

    assert {first["id"], second["id"]} == {a, b}
    assert first["id"] != second["id"]  # the one just shown loses the tie next time


def test_expired_message_is_never_selected(conn, monkeypatch):
    import time

    now = time.time()
    insert(conn, priority=0, expires_at=now - 10)  # already expired
    still_good = insert(conn, priority=99, expires_at=None)
    selector = Selector()
    row = selector.current(conn)
    assert row["id"] == still_good


def test_future_starts_at_is_not_yet_eligible(conn):
    import time

    now = time.time()
    insert(conn, priority=0, starts_at=now + 3600)  # an hour from now
    eligible_now = insert(conn, priority=99)
    selector = Selector()
    row = selector.current(conn)
    assert row["id"] == eligible_now


def test_holds_current_pick_until_dwell_elapses(conn, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr("service.selection.time.time", lambda: clock["t"])

    held = insert(conn, priority=50, dwell_seconds=300)
    selector = Selector()
    first = selector.current(conn)
    assert first["id"] == held

    # A higher-priority message arrives mid-dwell — should NOT preempt.
    insert(conn, priority=0, dwell_seconds=300)
    clock["t"] += 10
    still_held = selector.current(conn)
    assert still_held["id"] == held

    # Dwell has now elapsed — reselection should pick the higher-priority one.
    clock["t"] += 300
    reselected = selector.current(conn)
    assert reselected["id"] != held


def test_pinned_message_preempts_an_in_progress_dwell(conn, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr("service.selection.time.time", lambda: clock["t"])

    held = insert(conn, priority=50, dwell_seconds=300)
    selector = Selector()
    first = selector.current(conn)
    assert first["id"] == held

    clock["t"] += 5
    pinned_id = insert(conn, priority=99, pinned=True, dwell_seconds=300)
    row = selector.current(conn)
    assert row["id"] == pinned_id


def test_force_bypasses_dwell_hold(conn, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr("service.selection.time.time", lambda: clock["t"])

    a = insert(conn, priority=10, dwell_seconds=300)
    selector = Selector()
    first = selector.current(conn)
    assert first["id"] == a

    b = insert(conn, priority=5, dwell_seconds=300)
    clock["t"] += 1
    forced = selector.current(conn, force=True)
    assert forced["id"] == b


def test_no_eligible_messages_returns_none(conn):
    selector = Selector()
    assert selector.current(conn) is None
