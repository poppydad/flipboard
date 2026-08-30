from datetime import datetime, timedelta, timezone

import pytest

from service.channels import mufc
from service.compose import CHARSET, COLS, ROWS

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _decode(grid: list[int]) -> str:
    rows = []
    for r in range(ROWS):
        row = grid[r * COLS : (r + 1) * COLS]
        rows.append("".join(CHARSET.char_for(c) or " " for c in row))
    return "\n".join(rows)


def _event(kickoff, opponent="Arsenal", home=True, completed=False, us_score=None, them_score=None):
    """One ESPN schedule event, shaped like the real payload."""

    def side(name, score):
        c = {"team": {"shortDisplayName": name}}
        if score is not None:
            c["score"] = {"value": float(score), "displayValue": str(score)}
        return c

    us = side("Man United", us_score)
    them = side(opponent, them_score)
    us["homeAway"] = "home" if home else "away"
    them["homeAway"] = "away" if home else "home"
    return {
        "date": kickoff.strftime("%Y-%m-%dT%H:%MZ"),
        "competitions": [
            {"competitors": [us, them], "status": {"type": {"completed": completed}}}
        ],
    }


@pytest.fixture
def api(monkeypatch):
    """Wire the two ESPN endpoints: played matches, and upcoming fixtures."""
    state = {"played": [], "fixtures": []}

    def fake_get_json(url, **params):
        return {"events": state["fixtures"] if params.get("fixture") else state["played"]}

    monkeypatch.setattr(mufc, "get_json", fake_get_json)
    monkeypatch.setattr(mufc, "_now", lambda: NOW)
    return state


# --- countdown ----------------------------------------------------------


def test_days_out_counts_down_in_days(api):
    api["fixtures"] = [_event(NOW + timedelta(days=3, hours=4), "Arsenal")]
    text = _decode(mufc.run().grid)
    assert "MUFC VS ARSENAL" in text
    assert "3" in text and "DAYS" in text


def test_exactly_one_day_is_singular(api):
    # "1 DAYS" gets a whole 22-column row to itself; the plural is not cosmetic.
    api["fixtures"] = [_event(NOW + timedelta(days=1, hours=22), "Ipswich")]
    text = _decode(mufc.run().grid)
    assert "1" in text
    assert "DAY" in text
    assert "DAYS" not in text


def test_away_fixture_says_at_not_v(api):
    api["fixtures"] = [_event(NOW + timedelta(days=2), "Everton", home=False)]
    assert "MUFC AT EVERTON" in _decode(mufc.run().grid)


def test_hours_when_kickoff_is_today(api):
    api["fixtures"] = [_event(NOW + timedelta(hours=5), "Fulham")]
    text = _decode(mufc.run().grid)
    assert "5" in text and "HOURS" in text


def test_nearest_fixture_wins_not_the_first_listed(api):
    api["fixtures"] = [
        _event(NOW + timedelta(days=9), "Leeds"),
        _event(NOW + timedelta(days=2), "Everton"),
    ]
    assert "EVERTON" in _decode(mufc.run().grid)


def test_fixture_beyond_the_horizon_is_not_worth_a_countdown(api):
    api["fixtures"] = [_event(NOW + timedelta(days=40), "Chelsea")]
    assert mufc.run() is None


def test_a_fixture_already_kicked_off_is_not_upcoming(api):
    api["fixtures"] = [_event(NOW - timedelta(hours=1), "Chelsea")]
    assert mufc.run() is None


# --- results ------------------------------------------------------------


def test_recent_win_shows_the_scoreline(api):
    api["played"] = [
        _event(NOW - timedelta(hours=6), "Arsenal", completed=True, us_score=2, them_score=1)
    ]
    text = _decode(mufc.run().grid)
    assert "WON" in text
    assert "MUFC 2-1 ARSENAL" in text


def test_recent_loss_says_lost(api):
    api["played"] = [
        _event(NOW - timedelta(hours=6), "Hull", completed=True, us_score=0, them_score=2)
    ]
    text = _decode(mufc.run().grid)
    assert "LOST" in text
    assert "MUFC 0-2 HULL" in text


def test_draw_says_drew(api):
    api["played"] = [
        _event(NOW - timedelta(hours=6), "Everton", completed=True, us_score=1, them_score=1)
    ]
    assert "DREW" in _decode(mufc.run().grid)


def test_double_digit_score_compares_numerically_not_as_text(api):
    # "10" > "9" is False as strings — a 10-9 win would have read as LOST.
    api["played"] = [
        _event(NOW - timedelta(hours=6), "Oldham", completed=True, us_score=10, them_score=9)
    ]
    assert "WON" in _decode(mufc.run().grid)


def test_a_result_is_preferred_over_the_next_countdown(api):
    api["played"] = [
        _event(NOW - timedelta(hours=3), "Arsenal", completed=True, us_score=3, them_score=0)
    ]
    api["fixtures"] = [_event(NOW + timedelta(days=4), "Everton")]
    text = _decode(mufc.run().grid)
    assert "WON" in text
    assert "EVERTON" not in text


def test_a_stale_result_falls_through_to_the_countdown(api):
    api["played"] = [
        _event(NOW - timedelta(days=5), "Arsenal", completed=True, us_score=3, them_score=0)
    ]
    api["fixtures"] = [_event(NOW + timedelta(days=4), "Everton")]
    text = _decode(mufc.run().grid)
    assert "MUFC VS EVERTON" in text
    assert "WON" not in text


def test_an_in_progress_match_is_not_reported_as_a_result(api):
    api["played"] = [
        _event(NOW - timedelta(hours=1), "Arsenal", completed=False, us_score=1, them_score=0)
    ]
    assert mufc.run() is None


# --- the API being unhelpful --------------------------------------------


def test_network_failure_posts_nothing_rather_than_raising(monkeypatch):
    monkeypatch.setattr(mufc, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(mufc, "_now", lambda: NOW)
    assert mufc.run() is None


def test_malformed_event_is_skipped_not_fatal(api):
    api["fixtures"] = [{"date": "not-a-date"}, _event(NOW + timedelta(days=2), "Everton")]
    assert "EVERTON" in _decode(mufc.run().grid)


def test_a_match_we_are_not_in_is_ignored(api):
    odd = _event(NOW + timedelta(days=1), "Everton")
    odd["competitions"][0]["competitors"][0]["team"]["shortDisplayName"] = "Chelsea"
    api["fixtures"] = [odd]
    assert mufc.run() is None


def test_output_is_always_a_full_valid_grid(api):
    api["fixtures"] = [_event(NOW + timedelta(days=2), "Wolverhampton Wanderers")]
    grid = mufc.run().grid
    assert len(grid) == ROWS * COLS
    for code in grid:
        assert 0 <= code < CHARSET.size


def test_channel_polls_every_five_minutes(api):
    assert mufc.CHANNEL.name == "mufc"
    assert mufc.CHANNEL.cron == "*/5 * * * *"


# --- live match ---------------------------------------------------------


def _live(kickoff, opponent="Ipswich", home=True, us_score=0, them_score=0, clock="74'"):
    e = _event(kickoff, opponent, home=home, us_score=us_score, them_score=them_score)
    e["competitions"][0]["status"] = {
        "displayClock": clock,
        "type": {"state": "in", "completed": False, "detail": clock},
    }
    return e


def test_a_match_in_progress_shows_the_running_score(api):
    api["fixtures"] = [_live(NOW - timedelta(minutes=74), us_score=4, them_score=1)]
    text = _decode(mufc.run().grid)
    assert "LIVE 74'" in text
    assert "MUFC 4-1 IPSWICH" in text


def test_a_live_match_is_pinned_so_nothing_else_shows(api):
    # "not display anything else for the match duration" — pinned is the
    # mechanism the selector already has for that.
    api["fixtures"] = [_live(NOW - timedelta(minutes=20))]
    assert mufc.run().pinned is True


def test_a_live_scoreline_expires_quickly(api):
    # If the feed stops saying "in", a pinned board must not outlast the game.
    import time

    api["fixtures"] = [_live(NOW - timedelta(minutes=20))]
    minutes = (mufc.run().expires_at - time.time()) / 60
    assert 10 < minutes < 20


def test_live_outranks_both_the_result_and_the_countdown(api):
    api["played"] = [
        _event(NOW - timedelta(hours=3), "Arsenal", completed=True, us_score=3, them_score=0)
    ]
    api["fixtures"] = [
        _live(NOW - timedelta(minutes=30), "Ipswich", us_score=1, them_score=1),
        _event(NOW + timedelta(days=4), "Everton"),
    ]
    text = _decode(mufc.run().grid)
    assert "LIVE" in text
    assert "WON" not in text and "EVERTON" not in text


def test_a_finished_match_is_not_treated_as_live(api):
    api["fixtures"] = [_event(NOW - timedelta(hours=2), "Ipswich", completed=True, us_score=2, them_score=0)]
    assert mufc.run() is None  # 'completed' without state 'in' is not live


def test_a_live_match_with_no_score_yet_is_still_shown(api):
    api["fixtures"] = [_live(NOW - timedelta(minutes=3), clock="3'", us_score=0, them_score=0)]
    assert "MUFC 0-0 IPSWICH" in _decode(mufc.run().grid)
