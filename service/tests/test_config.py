from datetime import datetime, time

from service import config
from service.config import is_quiet_hours


def test_wrapping_window_default_config():
    # Default QUIET_HOURS_START/END is 20:00 -> 07:00, wrapping past midnight.
    late_night = datetime(2026, 1, 1, 23, 0)
    early_morning = datetime(2026, 1, 2, 3, 0)
    midday = datetime(2026, 1, 1, 14, 0)
    exactly_start = datetime(2026, 1, 1, 20, 0)
    exactly_end = datetime(2026, 1, 2, 7, 0)

    assert is_quiet_hours(late_night) is True
    assert is_quiet_hours(early_morning) is True
    assert is_quiet_hours(midday) is False
    assert is_quiet_hours(exactly_start) is True  # start boundary is inclusive
    assert is_quiet_hours(exactly_end) is False  # end boundary is exclusive — wakes right at quiet_end


def test_disabled_by_env_override_is_never_quiet(monkeypatch):
    # FLIPBOARD_QUIET_HOURS=off, resolved to this flag at import.
    monkeypatch.setattr(config, "QUIET_HOURS_ENABLED", False)

    # 3am, squarely inside the default window, is still not quiet.
    assert is_quiet_hours(datetime(2026, 1, 2, 3, 0)) is False


def test_snooze_suppresses_quiet_hours_until_it_expires(monkeypatch):
    # The phone form's "keep the board on until morning" button.
    deep_in_the_window = datetime(2026, 1, 2, 3, 0)
    assert is_quiet_hours(deep_in_the_window) is True

    snooze_until = datetime(2026, 1, 2, 7, 0).timestamp()
    monkeypatch.setattr(config.settings, "quiet_snooze_until", lambda: snooze_until)

    assert is_quiet_hours(deep_in_the_window) is False  # snoozed
    # ...and the moment it lapses, quiet hours is back on its own, with
    # nobody having to remember to turn it on again.
    assert is_quiet_hours(datetime(2026, 1, 3, 3, 0)) is True


def test_next_quiet_end_is_the_upcoming_seven_am(monkeypatch):
    # Evening: the next 07:00 is tomorrow's.
    assert config.next_quiet_end(datetime(2026, 1, 1, 21, 30)) == datetime(2026, 1, 2, 7, 0)
    # Small hours: it's later the same morning, so an overnight snooze
    # can't stretch into a second night.
    assert config.next_quiet_end(datetime(2026, 1, 2, 2, 0)) == datetime(2026, 1, 2, 7, 0)


def test_same_day_window_that_does_not_wrap(monkeypatch):
    # e.g. a midday nap window, 13:00-15:00 — start < end, no midnight wrap.
    monkeypatch.setattr(config, "QUIET_HOURS_START", time(13, 0))
    monkeypatch.setattr(config, "QUIET_HOURS_END", time(15, 0))

    assert is_quiet_hours(datetime(2026, 1, 1, 14, 0)) is True
    assert is_quiet_hours(datetime(2026, 1, 1, 12, 0)) is False
    assert is_quiet_hours(datetime(2026, 1, 1, 16, 0)) is False
