from datetime import datetime, time

from service import config
from service.config import is_quiet_hours


def test_wrapping_window_default_config():
    # Default QUIET_HOURS_START/END is 21:00 -> 07:00, wrapping past midnight.
    late_night = datetime(2026, 1, 1, 23, 0)
    early_morning = datetime(2026, 1, 2, 3, 0)
    midday = datetime(2026, 1, 1, 14, 0)
    exactly_start = datetime(2026, 1, 1, 21, 0)
    exactly_end = datetime(2026, 1, 2, 7, 0)

    assert is_quiet_hours(late_night) is True
    assert is_quiet_hours(early_morning) is True
    assert is_quiet_hours(midday) is False
    assert is_quiet_hours(exactly_start) is True  # start boundary is inclusive
    assert is_quiet_hours(exactly_end) is False  # end boundary is exclusive — wakes right at quiet_end


def test_same_day_window_that_does_not_wrap(monkeypatch):
    # e.g. a midday nap window, 13:00-15:00 — start < end, no midnight wrap.
    monkeypatch.setattr(config, "QUIET_HOURS_START", time(13, 0))
    monkeypatch.setattr(config, "QUIET_HOURS_END", time(15, 0))

    assert is_quiet_hours(datetime(2026, 1, 1, 14, 0)) is True
    assert is_quiet_hours(datetime(2026, 1, 1, 12, 0)) is False
    assert is_quiet_hours(datetime(2026, 1, 1, 16, 0)) is False
