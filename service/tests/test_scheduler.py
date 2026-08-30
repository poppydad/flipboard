import sqlite3
import time

import pytest

from service.channels.base import Channel, ChannelMessage
from service.channels.scheduler import run_channel
from service.compose import COLS, ROWS
from service.db import SCHEMA
from service.messages import create_message
from service.selection import Selector


class _NoCloseConnection:
    """Delegates to a real connection but swallows close() — run_channel
    legitimately closes the connection it opens when done, which would
    otherwise destroy this in-memory db before the test can assert
    against it (closing a :memory: connection discards the data)."""

    def __init__(self, real: sqlite3.Connection):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def close(self):
        pass


@pytest.fixture
def conn(monkeypatch):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.commit()

    # run_channel opens its own connection via db.get_connection() rather
    # than taking one as a parameter — it has to, since it's what the
    # scheduler calls directly with no request context. Point it at this
    # in-memory db for the test instead of a real file.
    monkeypatch.setattr("service.channels.scheduler.db.get_connection", lambda: _NoCloseConnection(c))
    yield c
    c.close()


def test_channel_message_gets_inserted(conn, monkeypatch):
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)
    channel = Channel(
        name="weather",
        cron="0 6 * * *",
        run=lambda: ChannelMessage(text="72F SUNNY", priority=20),
    )

    run_channel(channel)

    row = conn.execute("SELECT * FROM messages WHERE source = 'weather'").fetchone()
    assert row is not None
    assert row["raw_text"] == "72F SUNNY"
    assert row["priority"] == 20


def test_channel_returning_none_posts_nothing(conn, monkeypatch):
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)
    channel = Channel(name="calendar", cron="0 7 * * *", run=lambda: None)

    run_channel(channel)

    count = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
    assert count == 0


def test_channel_skipped_entirely_during_quiet_hours(conn, monkeypatch):
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: True)
    called = []
    channel = Channel(
        name="weather",
        cron="0 6 * * *",
        run=lambda: called.append(1) or ChannelMessage(text="SHOULD NOT POST"),
    )

    run_channel(channel)

    assert called == []  # channel.run() never even gets called during quiet hours
    count = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
    assert count == 0


def test_channel_that_raises_does_not_propagate(conn, monkeypatch):
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)

    def broken():
        raise RuntimeError("upstream API is down")

    channel = Channel(name="markets", cron="15 16 * * 1-5", run=broken)

    run_channel(channel)  # must not raise — a bad channel shouldn't crash the scheduler

    count = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
    assert count == 0


# --- superseding a channel's previous message --------------------------------
#
# Every test above fires a channel exactly once, which is why unbounded
# accumulation was invisible: the bug only exists on the second firing.
# These fire twice or more.


def _eligible(conn, now=None):
    now = now if now is not None else time.time()
    return conn.execute(
        "SELECT * FROM messages WHERE expires_at IS NULL OR expires_at > ? ORDER BY id",
        (now,),
    ).fetchall()


def test_second_firing_supersedes_the_first(conn, monkeypatch):
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)
    values = iter(["LIGHTS OUT 3 DAYS", "LIGHTS OUT 2 DAYS"])
    channel = Channel(name="f1", cron="0 * * * *", run=lambda: ChannelMessage(text=next(values)))

    run_channel(channel)
    run_channel(channel)

    live = _eligible(conn)
    assert len(live) == 1, "a channel's newest message should be the only eligible one"
    assert live[0]["raw_text"] == "LIGHTS OUT 2 DAYS"


def test_superseded_row_is_expired_not_deleted(conn, monkeypatch):
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)
    values = iter(["FIRST", "SECOND"])
    channel = Channel(name="f1", cron="0 * * * *", run=lambda: ChannelMessage(text=next(values)))

    run_channel(channel)
    run_channel(channel)

    all_rows = conn.execute("SELECT * FROM messages ORDER BY id").fetchall()
    assert len(all_rows) == 2, "history is kept — superseding expires, it doesn't DELETE"
    assert all_rows[0]["expires_at"] is not None
    assert all_rows[1]["expires_at"] is None


def test_hourly_polling_never_accumulates(conn, monkeypatch):
    """The actual regression: f1 polls hourly for 14 days before a race.
    Before the fix this left 336 permanent rows and the board sat on the
    stalest of them."""
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)
    hour = {"n": 0}

    def run():
        hour["n"] += 1
        return ChannelMessage(text=f"LIGHTS OUT {14 - hour['n'] // 24} DAYS", priority=15)

    channel = Channel(name="f1", cron="0 * * * *", run=run)
    for _ in range(14 * 24):
        run_channel(channel)

    live = _eligible(conn)
    assert len(live) == 1, f"336 polls should leave 1 eligible message, not {len(live)}"
    assert live[0]["raw_text"] == "LIGHTS OUT 0 DAYS", "the newest countdown, not the oldest"


def test_supersede_is_scoped_to_the_channel(conn, monkeypatch):
    """A channel must never expire another channel's message, or a manual
    one — POST /message posts at source='manual' and is not a channel."""
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)
    create_message(conn, source="manual", text="DINNER AT SEVEN", priority=50)
    run_channel(Channel(name="weather", cron="30 6 * * *", run=lambda: ChannelMessage(text="72F")))
    run_channel(Channel(name="f1", cron="0 * * * *", run=lambda: ChannelMessage(text="RACE DAY")))
    run_channel(Channel(name="f1", cron="0 * * * *", run=lambda: ChannelMessage(text="LIGHTS OUT")))

    live = {r["source"]: r["raw_text"] for r in _eligible(conn)}
    assert live == {"manual": "DINNER AT SEVEN", "weather": "72F", "f1": "LIGHTS OUT"}


def test_polling_channel_leaves_no_backlog_ahead_of_a_manual_message(conn, monkeypatch):
    """What superseding actually fixes. f1 outranks manual by priority (15
    vs 50) and legitimately preempts it while it has something live to say
    — that's §9's selection rule, not a bug. The bug was the *backlog*:
    a week of hourly polls left 168 permanent rows, so manual stayed buried
    for ~14 hours of dwell even after f1 had nothing current to say.
    Now exactly one f1 row ever competes, and manual surfaces the moment
    it expires."""
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)
    monkeypatch.setattr("service.selection.is_quiet_hours", lambda: False)

    channel = Channel(name="f1", cron="0 * * * *", run=lambda: ChannelMessage(text="LIGHTS OUT", priority=15))
    for _ in range(7 * 24):
        run_channel(channel)
    create_message(conn, source="manual", text="DINNER AT SEVEN", priority=50)

    ahead = [r for r in _eligible(conn) if r["priority"] < 50]
    assert len(ahead) == 1, f"168 polls should leave 1 row ahead of manual, not {len(ahead)}"

    # once the channel's single live message expires, manual is next up —
    # previously it waited out 167 more stale rows first.
    conn.execute("UPDATE messages SET expires_at = ? WHERE source = 'f1'", (time.time() - 1,))
    conn.commit()
    assert Selector().current(conn, force=True)["source"] == "manual"


def test_multi_page_channel_message_survives_its_own_supersede(conn, monkeypatch):
    """Supersede runs before the insert and in the same transaction, so a
    paginated channel message must not expire its own later pages."""
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)
    long_text = " ".join(f"WORD{i}" for i in range(60))
    channel = Channel(name="calendar", cron="0 7 * * *", run=lambda: ChannelMessage(text=long_text))

    run_channel(channel)
    run_channel(channel)

    live = _eligible(conn)
    assert len(live) > 1, "a paginated message should keep all of its pages eligible"
    assert all(r["raw_text"] == long_text for r in live)


# --- an unchanged poll is not news --------------------------------------


def _channel(grid, pinned=False, expires_at=None):
    from service.channels.base import Channel, ChannelMessage

    return Channel(
        name="mufc",
        cron="*/5 * * * *",
        run=lambda: ChannelMessage(grid=grid, pinned=pinned, expires_at=expires_at, dwell_seconds=300),
    )


def test_an_identical_repost_bumps_the_expiry_instead_of_inserting(conn, monkeypatch):
    # A live scoreline sits unchanged for most of a match. Five-minute polls
    # must not write a new row each time — that resets last_shown to
    # never-shown every cycle and distorts the rotation.
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)

    grid = [0] * (ROWS * COLS)
    run_channel(_channel(grid, pinned=True, expires_at=1_800_000_000.0))
    run_channel(_channel(grid, pinned=True, expires_at=1_900_000_000.0))

    rows = conn.execute("SELECT id, expires_at FROM messages WHERE source = 'mufc'").fetchall()
    assert len(rows) == 1                       # one row, not two
    assert rows[0]["expires_at"] == 1_900_000_000.0  # and it was kept alive


def test_a_changed_scoreline_does_insert(conn, monkeypatch):
    monkeypatch.setattr("service.channels.scheduler.is_quiet_hours", lambda: False)

    run_channel(_channel([0] * (ROWS * COLS)))
    run_channel(_channel([1] + [0] * (ROWS * COLS - 1)))  # a goal

    live = conn.execute(
        "SELECT COUNT(*) AS n FROM messages WHERE source = 'mufc' AND expires_at IS NULL"
    ).fetchone()
    assert live["n"] == 1  # the old one was superseded, the new one stands
