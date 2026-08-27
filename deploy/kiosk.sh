#!/bin/sh
# Launches the board full-screen on the Pi's display. Run from labwc's
# autostart, so it fires once the Wayland session is up.
#
# Three things this has to get right, none of which Chromium does on its own:
#
#   1. Don't race the service. systemd starts flipboard.service and labwc
#      concurrently; Chromium pointed at a port nothing is listening on yet
#      shows an error page and stays there. So: wait for the port.
#   2. Don't let the panel blank. A hallway board that sleeps after 10
#      minutes isn't a board. swayidle is what would do the blanking.
#   3. Don't reuse the normal browser profile. A crash flag or restore-tabs
#      prompt in the everyday profile would land on the board.

URL="http://localhost:8000/display.html"

pkill -x swayidle 2>/dev/null
wlopm --on '*' 2>/dev/null

# ~30s of grace, then launch anyway — a visible error beats a black screen
# with no clue why.
i=0
while [ "$i" -lt 60 ]; do
    if curl -sf -o /dev/null "http://localhost:8000/current"; then break; fi
    i=$((i + 1))
    sleep 0.5
done

exec chromium \
    --kiosk \
    --ozone-platform=wayland \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=Translate \
    --check-for-update-interval=31536000 \
    --user-data-dir="$HOME/.config/flipboard-kiosk" \
    "$URL"
