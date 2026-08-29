#!/bin/sh
# Powers the physical panel off during quiet hours, and back on after.
#
# Why this exists: the service already sends `brightness: 0.0` during quiet
# hours and the renderer honours it, but a "black" LCD is still a lit panel
# — in a dark hallway it's a faintly glowing rectangle, not darkness. The
# proper fix would be dimming the monitor's own backlight over DDC/CI, but
# the ARZOPA panel here doesn't implement it (ddcutil reads its EDID fine
# and gets nothing at I2C address 0x37), and no HDMI monitor exposes
# /sys/class/backlight. So: cut the output entirely with wlopm.
#
# It follows GET /current's `brightness` rather than reimplementing the
# schedule. That field is already the contract between the service and the
# renderer, and it accounts for the phone form's snooze and the
# FLIPBOARD_QUIET_HOURS override for free. Inventing a second source of
# truth here would be a second thing to get out of sync.

POLL_SECONDS=30
last=""

while true; do
    brightness=$(curl -sf --max-time 5 http://localhost:8000/current \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["brightness"])' 2>/dev/null)

    # Unreachable service or garbled reply: leave the panel alone. Failing
    # towards "on" would light the board at 3am; failing towards "off"
    # would blank it all day. Doing nothing keeps whatever was already
    # correct until the service answers again.
    if [ -n "$brightness" ]; then
        case "$brightness" in
            0|0.0) want="off" ;;
            *) want="on" ;;
        esac

        if [ "$want" != "$last" ]; then
            wlopm --"$want" '*' >/dev/null 2>&1 && last="$want"
        fi
    fi

    sleep "$POLL_SECONDS"
done
