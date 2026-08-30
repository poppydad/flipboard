"""
f1 channel (build plan §11): countdown to lights-out before a race,
top-3 results for a couple of days after. Data from OpenF1 (free,
keyless — https://openf1.org).

Runs hourly and decides for itself whether there's anything worth
posting — "race weekends" aren't a fixed schedule, so the cron here is
just a polling cadence, not the actual trigger condition.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..compose.templates import countdown, list_template
from .base import Channel, ChannelMessage, countdown_parts, expires_in
from .http import get_json

_BASE = "https://api.openf1.org/v1"
_RESULTS_WINDOW = timedelta(days=2)  # how long after a race its results stay postable
_COUNTDOWN_HORIZON = timedelta(days=14)  # don't show a countdown further out than this
# Re-confirmed every five minutes while the race runs; short so a pinned
# board can't outlast the chequered flag if the feed goes quiet.
_LIVE_EXPIRY_HOURS = 0.25


def _get(path: str, **params) -> list[dict] | None:
    result = get_json(f"{_BASE}/{path}", **params)
    return result if isinstance(result, list) else None


def _now() -> datetime:
    # A thin wrapper so tests can monkeypatch "the current time" directly —
    # datetime is an immutable C type, its .now() can't be patched in place.
    return datetime.now(timezone.utc)


def _next_or_last_race(now: datetime) -> tuple[dict, bool] | None:
    """The race session nearest to `now` in either direction: (session, is_upcoming)."""
    sessions = _get("sessions", year=now.year, session_name="Race")
    if not sessions:
        return None

    parsed = []
    for s in sessions:
        try:
            start = datetime.fromisoformat(s["date_start"])
        except (KeyError, ValueError, TypeError):
            continue
        parsed.append((start, s))

    upcoming = sorted((p for p in parsed if p[0] > now), key=lambda p: p[0])
    if upcoming:
        return upcoming[0][1], True

    past = sorted((p for p in parsed if p[0] <= now), key=lambda p: p[0], reverse=True)
    if past:
        return past[0][1], False

    return None


def _live_message(session: dict, now: datetime) -> ChannelMessage | None:
    """The top three right now, if the race is actually running.

    Pinned for the duration, so the board is the timing screen and nothing
    else takes a turn.

    `/position` is a log of every position change, not a standings
    snapshot, so this filters to the podium places and keeps the most
    recent record for each — the last time anyone took P1 is who holds P1.
    """
    try:
        start = datetime.fromisoformat(session["date_start"])
        end = datetime.fromisoformat(session["date_end"])
    except (KeyError, ValueError, TypeError):
        return None
    if not start <= now <= end:
        return None

    key = session.get("session_key")
    records = _get("position", session_key=key, **{"position<=": 3})
    drivers = _get("drivers", session_key=key)
    if not records or not drivers:
        return None

    latest: dict[int, tuple[str, int]] = {}
    for r in records:
        place, when, who = r.get("position"), r.get("date"), r.get("driver_number")
        if place is None or when is None or who is None:
            continue
        if place not in latest or when > latest[place][0]:
            latest[place] = (when, who)
    if not latest:
        return None

    names = {d.get("driver_number"): d.get("name_acronym", "???") for d in drivers}
    items = [f"{p} {names.get(latest[p][1], '???')}" for p in sorted(latest)]

    return ChannelMessage(
        grid=list_template("LIVE", items),
        priority=5,
        dwell_seconds=300,
        pinned=True,
        expires_at=expires_in(_LIVE_EXPIRY_HOURS),
    )


def _countdown_message(session: dict, now: datetime) -> ChannelMessage | None:
    start = datetime.fromisoformat(session["date_start"])
    remaining = start - now
    if remaining > _COUNTDOWN_HORIZON:
        return None

    number, unit = countdown_parts(remaining)
    grid = countdown("LIGHTS OUT", number, unit)
    return ChannelMessage(grid=grid, priority=15, dwell_seconds=300, expires_at=expires_in(3))


def _results_message(session: dict, now: datetime) -> ChannelMessage | None:
    end_raw = session.get("date_end") or session["date_start"]
    end = datetime.fromisoformat(end_raw)
    if now - end > _RESULTS_WINDOW:
        return None

    session_key = session["session_key"]
    results = _get("session_result", session_key=session_key)
    drivers = _get("drivers", session_key=session_key)
    if not results or not drivers:
        return None

    names = {d.get("driver_number"): d.get("name_acronym", "???") for d in drivers}
    top3 = sorted(
        (r for r in results if isinstance(r.get("position"), int)),
        key=lambda r: r["position"],
    )[:3]
    if not top3:
        return None

    items = [f"{r['position']} {names.get(r.get('driver_number'), '???')}" for r in top3]
    grid = list_template("RESULTS", items)
    return ChannelMessage(grid=grid, priority=15, dwell_seconds=300, expires_at=expires_in(3))


def run() -> ChannelMessage | None:
    now = _now()
    found = _next_or_last_race(now)
    if found is None:
        return None

    session, is_upcoming = found
    if is_upcoming:
        return _countdown_message(session, now)
    # _next_or_last_race returns the most recent past race, which is the one
    # in progress while it's running — check that before calling it history.
    return _live_message(session, now) or _results_message(session, now)


# Every five minutes, so a podium change during a race reaches the board.
# Off a race weekend this is a cheap no-op poll; during one it's the point.
CHANNEL = Channel(name="f1", cron="*/5 * * * *", run=run)
