import sqlite3

import pytest

from service import settings
from service.db import SCHEMA


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.commit()
    yield c
    c.close()


@pytest.fixture(autouse=True)
def clean_cache():
    # settings caches in a module global so is_quiet_hours() isn't a database
    # round trip every 5 seconds. That makes it leak across tests unless it's
    # put back.
    before = settings.quiet_snooze_until()
    yield
    settings._snooze_until = before


def test_snooze_round_trips_through_the_database(conn):
    settings.set_quiet_snooze(conn, 1793000000.0)
    assert settings.quiet_snooze_until() == 1793000000.0

    # A restart: cache dropped, value reloaded from disk.
    settings._snooze_until = None
    settings.load(conn)
    assert settings.quiet_snooze_until() == 1793000000.0


def test_clearing_the_snooze_removes_it(conn):
    settings.set_quiet_snooze(conn, 1793000000.0)
    settings.set_quiet_snooze(conn, None)
    assert settings.quiet_snooze_until() is None

    settings.load(conn)
    assert settings.quiet_snooze_until() is None


def test_load_on_a_fresh_database_is_none(conn):
    settings._snooze_until = 12345.0  # stale value from somewhere else
    settings.load(conn)
    assert settings.quiet_snooze_until() is None


def test_setting_twice_updates_rather_than_conflicting(conn):
    settings.set_quiet_snooze(conn, 1.0)
    settings.set_quiet_snooze(conn, 2.0)  # ON CONFLICT DO UPDATE, not an IntegrityError
    settings.load(conn)
    assert settings.quiet_snooze_until() == 2.0
