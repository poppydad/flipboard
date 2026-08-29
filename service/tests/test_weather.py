from service.channels import weather
from service.compose import CHARSET, COLS, ROWS


def _decode(grid: list[int]) -> str:
    rows = []
    for r in range(ROWS):
        row = grid[r * COLS : (r + 1) * COLS]
        rows.append("".join(CHARSET.char_for(c) or " " for c in row))
    return "\n".join(rows)


def test_successful_fetch_produces_stat_grid(monkeypatch):
    monkeypatch.setattr(
        weather,
        "get_json",
        lambda *a, **k: {"current": {"temperature_2m": 68.6, "weather_code": 0}},
    )
    message = weather.run()
    text = _decode(message.grid)
    assert "69F" in text  # 68.6 rounds up
    assert "CLEAR SKY" in text
    assert message.priority == 25


def test_temperature_rounds_to_nearest_int(monkeypatch):
    monkeypatch.setattr(
        weather,
        "get_json",
        lambda *a, **k: {"current": {"temperature_2m": 72.5, "weather_code": 3}},
    )
    text = _decode(weather.run().grid)
    # round()'s banker's-rounding takes .5 to the nearest *even* int — 72, not 73.
    # Worth pinning explicitly so a future refactor to a different rounding
    # scheme (e.g. int(x + 0.5)) doesn't silently change displayed temps.
    assert "72F" in text
    assert "OVERCAST" in text


def test_unknown_weather_code_degrades_to_no_condition_not_a_crash(monkeypatch):
    monkeypatch.setattr(
        weather,
        "get_json",
        lambda *a, **k: {"current": {"temperature_2m": 50, "weather_code": 12345}},
    )
    message = weather.run()
    assert message is not None
    assert "50F" in _decode(message.grid)


def test_network_failure_returns_none(monkeypatch):
    monkeypatch.setattr(weather, "get_json", lambda *a, **k: None)
    assert weather.run() is None


def test_missing_temperature_field_returns_none(monkeypatch):
    monkeypatch.setattr(weather, "get_json", lambda *a, **k: {"current": {"weather_code": 0}})
    assert weather.run() is None


def test_channel_registered_with_correct_schedule():
    assert weather.CHANNEL.name == "weather"
    assert weather.CHANNEL.cron == "15 7,10,13,16,19 * * *"  # every 3h through the day


def test_a_reading_goes_stale_rather_than_lying(monkeypatch):
    # Found live: the 4:30pm reading was still claiming 82F at 11pm, because
    # channel messages had no expiry and _supersede only retires the previous
    # one when a *new* one lands.
    import time

    monkeypatch.setattr(weather, "get_json", lambda *a, **k: {"current": {"temperature_2m": 72.0, "weather_code": 0}})
    message = weather.run()
    assert message.expires_at is not None
    hours = (message.expires_at - time.time()) / 3600
    assert 3 < hours < 5  # longer than the 3h refresh, shorter than an evening
