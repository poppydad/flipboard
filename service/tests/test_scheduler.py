import sqlite3

import pytest

from service.channels.base import Channel, ChannelMessage
from service.channels.scheduler import run_channel
from service.db import SCHEMA


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
