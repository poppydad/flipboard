"""
weather channel (build plan §11): current conditions via Open-Meteo
(free, keyless — https://open-meteo.com), as a `stat` template.
Refreshes every three hours through the day.
"""
from __future__ import annotations

from ..compose.templates import stat
from .base import Channel, ChannelMessage, expires_in
from .http import get_json

LATITUDE = 40.304251
LONGITUDE = -74.776508

_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes (Open-Meteo's `weather_code`) -> a short board-friendly label.
_WEATHER_CODES = {
    0: "CLEAR SKY",
    1: "MOSTLY CLEAR",
    2: "PARTLY CLOUDY",
    3: "OVERCAST",
    45: "FOG",
    48: "FREEZING FOG",
    51: "LIGHT DRIZZLE",
    53: "DRIZZLE",
    55: "DENSE DRIZZLE",
    56: "FREEZING DRIZZLE",
    57: "FREEZING DRIZZLE",
    61: "LIGHT RAIN",
    63: "RAIN",
    65: "HEAVY RAIN",
    66: "FREEZING RAIN",
    67: "FREEZING RAIN",
    71: "LIGHT SNOW",
    73: "SNOW",
    75: "HEAVY SNOW",
    77: "SNOW GRAINS",
    80: "RAIN SHOWERS",
    81: "RAIN SHOWERS",
    82: "VIOLENT SHOWERS",
    85: "SNOW SHOWERS",
    86: "SNOW SHOWERS",
    95: "THUNDERSTORM",
    96: "THUNDERSTORM",
    99: "SEVERE STORM",
}


def run() -> ChannelMessage | None:
    data = get_json(
        _URL,
        latitude=LATITUDE,
        longitude=LONGITUDE,
        current="temperature_2m,weather_code",
        temperature_unit="fahrenheit",
    )
    if not isinstance(data, dict):
        return None

    current = data.get("current")
    if not current or current.get("temperature_2m") is None:
        return None

    temp = current["temperature_2m"]
    condition = _WEATHER_CODES.get(current.get("weather_code"), "")

    grid = stat("WEATHER", f"{round(temp)}F", condition)
    # Four hours: longer than the three-hour refresh so one failed fetch
    # doesn't blank it, short enough that an afternoon reading can't still
    # be on the board at bedtime.
    return ChannelMessage(grid=grid, priority=25, dwell_seconds=300, expires_at=expires_in(4))


# Every three hours through the day. Twice a day was too coarse: the 4:30pm
# reading was still claiming 82F at 11pm. The first run is just after quiet
# hours lift so the morning board isn't showing yesterday evening.
CHANNEL = Channel(name="weather", cron="15 7,10,13,16,19 * * *", run=run)
