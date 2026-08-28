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


@pytest.fixture(autouse=True)
def not_quiet_hours(monkeypatch):
    # Tests must not depend on what time it actually is when they run —
    # is_quiet_hours() is real wall-clock by default, and every test below
    # is about priority/dwell/pinned logic, not quiet hours. The dedicated
    # quiet-hours tests further down override this back to True themselves.
    monkeypatch.setattr("service.selection.is_quiet_hours", lambda: False)


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


def test_high_priority_message_does_not_monopolize_the_board(conn):
    # Regression, found live on the Pi: sorting by priority *before*
    # last_shown meant the lowest priority number won every reselection
    # forever. An f1 countdown (priority 15, no expiry) sat on the board for
    # the ten days until the race while weather, milestone, and everything
    # posted from a phone stayed invisible — the queue was full and nothing
    # rotated. Priority now decides who goes first, not who owns the board.
    important = insert(conn, priority=10, dwell_seconds=0)
    ordinary = insert(conn, priority=50, dwell_seconds=0)
    selector = Selector()

    first = selector.current(conn)
    assert first["id"] == important  # still goes first: both are never-shown

    second = selector.current(conn, force=True)
    assert second["id"] == ordinary  # ...but does not get to stay

    third = selector.current(conn, force=True)
    assert third["id"] == important  # and it comes back round


def test_pinned_beats_lower_priority_number(conn):
    insert(conn, priority=0)  # would win on priority alone
    pinned_id = insert(conn, priority=99, pinned=True)
    selector = Selector()
    row = selector.current(conn)
    assert row["id"] == pinned_id


def test_rapid_reselection_within_one_wall_clock_second_still_alternates(conn, monkeypatch):
    # Regression: shown_at used to default to SQLite's CURRENT_TIMESTAMP,
    # which only has 1-second resolution. Forced reselections faster than
    # that (e.g. a paginated message's pages cycling via /next) collided
    # on the same shown_at string and the tie-break silently fell back to
    # row order, getting stuck favoring the lower id forever. shown_at is
    # now an explicit Python epoch float instead — this proves sub-second
    # calls still alternate correctly.
    clock = {"t": 1000.0}
    monkeypatch.setattr("service.selection.time.time", lambda: clock["t"])

    a = insert(conn, priority=10, dwell_seconds=0)
    b = insert(conn, priority=10, dwell_seconds=0)
    selector = Selector()

    picks = []
    for _ in range(4):
        clock["t"] += 0.01  # sub-second — well within CURRENT_TIMESTAMP's dead zone
        picks.append(selector.current(conn, force=True)["id"])

    assert picks == [a, b, a, b]  # clean alternation, never stuck on one id


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


def test_pinned_message_preempts_an_already_pinned_message(conn, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr("service.selection.time.time", lambda: clock["t"])

    first_pinned = insert(conn, priority=50, pinned=True, dwell_seconds=300)
    selector = Selector()
    first = selector.current(conn)
    assert first["id"] == first_pinned

    clock["t"] += 5
    second_pinned = insert(conn, priority=50, pinned=True, dwell_seconds=300)
    row = selector.current(conn)
    assert row["id"] == second_pinned  # "show now" wins even over an already-pinned message


def test_pinned_rotation_does_not_flap_once_each_has_had_its_turn(conn, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr("service.selection.time.time", lambda: clock["t"])

    a = insert(conn, priority=50, pinned=True, dwell_seconds=300)
    b = insert(conn, priority=50, pinned=True, dwell_seconds=300)
    selector = Selector()

    first = selector.current(conn)
    assert first["id"] == a  # both never shown — tie goes to insertion order

    clock["t"] += 1
    second = selector.current(conn)
    assert second["id"] == b  # b hasn't shown yet either — preempts immediately

    clock["t"] += 1
    third = selector.current(conn)
    assert third["id"] == b  # both have shown once now — holds, doesn't flap back to a


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


# --- quiet hours -----------------------------------------------------------


def test_quiet_hours_excludes_non_pinned_even_at_top_priority(conn, monkeypatch):
    monkeypatch.setattr("service.selection.is_quiet_hours", lambda: True)
    insert(conn, priority=0)  # would win any time other than quiet hours
    selector = Selector()
    assert selector.current(conn) is None


def test_quiet_hours_still_shows_a_pinned_message(conn, monkeypatch):
    monkeypatch.setattr("service.selection.is_quiet_hours", lambda: True)
    insert(conn, priority=0)  # non-pinned, ignored during quiet hours
    pinned_id = insert(conn, priority=99, pinned=True)
    selector = Selector()
    row = selector.current(conn)
    assert row["id"] == pinned_id


def test_quiet_hours_onset_interrupts_an_already_showing_non_pinned_message(conn, monkeypatch):
    quiet = {"now": False}
    monkeypatch.setattr("service.selection.is_quiet_hours", lambda: quiet["now"])

    held = insert(conn, priority=50, dwell_seconds=300)
    selector = Selector()
    first = selector.current(conn)
    assert first["id"] == held

    quiet["now"] = True  # quiet hours begins mid-dwell
    assert selector.current(conn) is None  # goes blank, doesn't keep showing it


def test_quiet_hours_ending_reopens_non_pinned_candidates(conn, monkeypatch):
    quiet = {"now": True}
    monkeypatch.setattr("service.selection.is_quiet_hours", lambda: quiet["now"])

    normal_id = insert(conn, priority=10)
    selector = Selector()
    assert selector.current(conn) is None  # quiet hours, nothing pinned

    quiet["now"] = False  # the morning set — quiet hours ends
    row = selector.current(conn)
    assert row["id"] == normal_id
