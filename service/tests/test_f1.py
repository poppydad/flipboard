from datetime import datetime, timedelta, timezone

from service.channels import f1
from service.compose import CHARSET, COLS, ROWS


def _decode(grid: list[int]) -> str:
    rows = []
    for r in range(ROWS):
        row = grid[r * COLS : (r + 1) * COLS]
        rows.append("".join(CHARSET.char_for(c) or " " for c in row))
    return "\n".join(rows)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_no_sessions_at_all_returns_none(monkeypatch):
    monkeypatch.setattr(f1, "get_json", lambda *a, **k: None)
    assert f1.run() is None


def test_upcoming_race_within_a_day_shows_hours(monkeypatch):
    now = datetime(2026, 8, 23, 4, 0, tzinfo=timezone.utc)
    race_start = now + timedelta(hours=9)

    def fake_get_json(url, **params):
        if "sessions" in url:
            return [{"session_name": "Race", "session_key": 1, "date_start": _iso(race_start)}]
        return None

    monkeypatch.setattr(f1, "get_json", fake_get_json)
    monkeypatch.setattr(f1, "_now", lambda: now)

    message = f1.run()
    text = _decode(message.grid)
    assert "LIGHTS OUT" in text
    assert "9" in text
    assert "HOURS" in text


def test_upcoming_race_several_days_out_shows_days(monkeypatch):
    now = datetime(2026, 8, 23, 4, 0, tzinfo=timezone.utc)
    race_start = now + timedelta(days=5, hours=2)

    def fake_get_json(url, **params):
        if "sessions" in url:
            return [{"session_name": "Race", "session_key": 1, "date_start": _iso(race_start)}]
        return None

    monkeypatch.setattr(f1, "get_json", fake_get_json)
    monkeypatch.setattr(f1, "_now", lambda: now)

    text = _decode(f1.run().grid)
    assert "5" in text
    assert "DAYS" in text


def test_upcoming_race_beyond_horizon_returns_none(monkeypatch):
    now = datetime(2026, 8, 23, 4, 0, tzinfo=timezone.utc)
    race_start = now + timedelta(days=60)  # off-season, next season announced early

    def fake_get_json(url, **params):
        if "sessions" in url:
            return [{"session_name": "Race", "session_key": 1, "date_start": _iso(race_start)}]
        return None

    monkeypatch.setattr(f1, "get_json", fake_get_json)
    monkeypatch.setattr(f1, "_now", lambda: now)

    assert f1.run() is None


def test_recent_past_race_shows_top_3_results_by_position(monkeypatch):
    now = datetime(2026, 8, 23, 4, 0, tzinfo=timezone.utc)
    race_start = now - timedelta(hours=5)
    race_end = now - timedelta(hours=3)

    def fake_get_json(url, **params):
        if "sessions" in url:
            return [
                {
                    "session_name": "Race",
                    "session_key": 42,
                    "date_start": _iso(race_start),
                    "date_end": _iso(race_end),
                }
            ]
        if "session_result" in url:
            return [
                {"position": 2, "driver_number": 4},
                {"position": 1, "driver_number": 1},
                {"position": 3, "driver_number": 44},
                {"position": 4, "driver_number": 16},  # 4th place, should be excluded
            ]
        if "drivers" in url:
            return [
                {"driver_number": 1, "name_acronym": "VER"},
                {"driver_number": 4, "name_acronym": "NOR"},
                {"driver_number": 44, "name_acronym": "HAM"},
                {"driver_number": 16, "name_acronym": "LEC"},
            ]
        return None

    monkeypatch.setattr(f1, "get_json", fake_get_json)
    monkeypatch.setattr(f1, "_now", lambda: now)

    text = _decode(f1.run().grid)
    assert "1 VER" in text
    assert "2 NOR" in text
    assert "3 HAM" in text
    assert "4 LEC" not in text  # only top 3


def test_race_results_expire_after_the_window(monkeypatch):
    now = datetime(2026, 8, 23, 4, 0, tzinfo=timezone.utc)
    race_start = now - timedelta(days=5)
    race_end = race_start + timedelta(hours=2)  # ended well over 2 days ago

    def fake_get_json(url, **params):
        if "sessions" in url:
            return [
                {
                    "session_name": "Race",
                    "session_key": 42,
                    "date_start": _iso(race_start),
                    "date_end": _iso(race_end),
                }
            ]
        return None

    monkeypatch.setattr(f1, "get_json", fake_get_json)
    monkeypatch.setattr(f1, "_now", lambda: now)

    assert f1.run() is None


def test_missing_results_or_drivers_returns_none(monkeypatch):
    now = datetime(2026, 8, 23, 4, 0, tzinfo=timezone.utc)
    race_start = now - timedelta(hours=5)
    race_end = now - timedelta(hours=3)

    def fake_get_json(url, **params):
        if "sessions" in url:
            return [
                {
                    "session_name": "Race",
                    "session_key": 42,
                    "date_start": _iso(race_start),
                    "date_end": _iso(race_end),
                }
            ]
        return None  # session_result and drivers both fail

    monkeypatch.setattr(f1, "get_json", fake_get_json)
    monkeypatch.setattr(f1, "_now", lambda: now)

    assert f1.run() is None


def test_channel_registered_with_hourly_polling_cadence():
    assert f1.CHANNEL.name == "f1"
    assert f1.CHANNEL.cron == "0 * * * *"
