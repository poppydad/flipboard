"""
mufc channel (build plan §11): countdown to the next Manchester United
fixture, the scoreline for a day or two after one finishes.

Data from ESPN's public site API (free, keyless). The build plan assumed
this channel needed a football-data.org key; it doesn't, the same way
weather (Open-Meteo) and f1 (OpenF1) turned out not to. Nothing here is
authenticated, so there is no key to rotate or leak.

Two endpoints, because ESPN splits them: the bare team schedule returns
matches already played, and `?fixture=true` returns the ones to come.

Runs hourly and decides for itself whether there's anything worth
posting — a fixture list isn't a fixed weekly rhythm once cup
competitions are in play, so the cron is a polling cadence, not the
trigger.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..compose.charset import COLS
from ..compose.templates import countdown, stat
from .base import Channel, ChannelMessage, countdown_parts, expires_in
from .http import get_json

# 360 is Manchester United; eng.1 is the Premier League. The team schedule
# covers every competition the team plays in, not just the league.
_SCHEDULE = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/360/schedule"

_RESULTS_WINDOW = timedelta(days=2)  # how long a finished result stays postable
_COUNTDOWN_HORIZON = timedelta(days=10)  # don't count down from further out than this

_US = "Man United"  # ESPN's shortDisplayName for the team itself
_NAME = "MUFC"  # what the board calls us


def _now() -> datetime:
    # Wrapper so tests can monkeypatch "now" — datetime is an immutable C
    # type and its .now() can't be patched in place. Same approach as f1.py.
    return datetime.now(timezone.utc)


def _events(fixtures: bool) -> list[dict]:
    payload = get_json(_SCHEDULE, **({"fixture": "true"} if fixtures else {}))
    if not isinstance(payload, dict):
        return []
    events = payload.get("events")
    return events if isinstance(events, list) else []


def _parse(event: dict) -> tuple[datetime, dict, dict] | None:
    """(kickoff, us, them) — or None if the event isn't shaped as expected."""
    try:
        # ESPN stamps these "...Z", which fromisoformat rejects before 3.11.
        kickoff = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
        competitors = event["competitions"][0]["competitors"]
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        return None

    us = them = None
    for c in competitors:
        name = (c.get("team") or {}).get("shortDisplayName")
        if name == _US:
            us = c
        else:
            them = c
    if us is None or them is None:
        return None
    return kickoff, us, them


def _opponent(them: dict) -> str:
    team = them.get("team") or {}
    return (team.get("shortDisplayName") or team.get("displayName") or "").upper()


def _countdown_message(now: datetime) -> ChannelMessage | None:
    upcoming = []
    for event in _events(fixtures=True):
        parsed = _parse(event)
        if parsed and parsed[0] > now:
            upcoming.append(parsed)
    if not upcoming:
        return None

    kickoff, us, them = min(upcoming, key=lambda p: p[0])
    remaining = kickoff - now
    if remaining > _COUNTDOWN_HORIZON:
        return None

    # Name both sides — "MUFC VS IPSWICH" reads as a fixture, where a bare
    # "VS IPSWICH" makes you supply the other half yourself. VS/AT still
    # carries home or away. If a long opponent pushes this past one row,
    # drop our own name rather than truncating theirs mid-word.
    prefix = "VS" if us.get("homeAway") == "home" else "AT"
    label = f"{_NAME} {prefix} {_opponent(them)}"
    if len(label) > COLS:
        label = f"{prefix} {_opponent(them)}"[:COLS]

    number, unit = countdown_parts(remaining)
    return ChannelMessage(grid=countdown(label, number, unit), priority=20, dwell_seconds=300, expires_at=expires_in(3))


def _score(competitor: dict) -> int | None:
    """Goals as an int.

    ESPN nests this as {"value": 2.0, "displayValue": "2", ...}, but has
    been seen returning a bare number too. Returning an int rather than the
    display string matters twice: comparing "10" > "9" as strings is False,
    and str(2.0) would put "2.0" on the board.
    """
    score = competitor.get("score")
    if isinstance(score, dict):
        score = score.get("value", score.get("displayValue"))
    try:
        return int(float(score))
    except (TypeError, ValueError):
        return None


def _results_message(now: datetime) -> ChannelMessage | None:
    played = []
    for event in _events(fixtures=False):
        parsed = _parse(event)
        if not parsed:
            continue
        try:
            if not event["competitions"][0]["status"]["type"]["completed"]:
                continue
        except (KeyError, IndexError, TypeError):
            continue
        played.append(parsed)
    if not played:
        return None

    kickoff, us, them = max(played, key=lambda p: p[0])
    if now - kickoff > _RESULTS_WINDOW:
        return None

    ours, theirs = _score(us), _score(them)
    if ours is None or theirs is None:
        return None

    if ours > theirs:
        verdict = "WON"
    elif ours < theirs:
        verdict = "LOST"
    else:
        verdict = "DREW"

    # stat() puts each field on its own fixed row, so keep the scoreline to
    # one: "MUFC 2-1 ARSENAL" leaves room for the longer club names.
    line = f"{_NAME} {ours}-{theirs} {_opponent(them)}"[:COLS]
    return ChannelMessage(grid=stat(verdict, line), priority=20, dwell_seconds=300, expires_at=expires_in(3))


def run() -> ChannelMessage | None:
    now = _now()
    # A just-finished match is the more interesting thing to say; only fall
    # back to counting down once its window has passed.
    return _results_message(now) or _countdown_message(now)


CHANNEL = Channel(name="mufc", cron="0 * * * *", run=run)
