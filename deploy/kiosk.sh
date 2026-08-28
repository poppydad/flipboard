#!/bin/sh
# Launches the board full-screen on the Pi's display. Started by
# deploy/kiosk.service — see the note there about why this isn't in labwc's
# autostart.
#
# Four things this has to get right, none of which Chromium does on its own:
#
#   1. Don't race the compositor. At boot this can start before labwc has
#      created the Wayland socket; Chromium then exits immediately with
#      "Missing X server or $DISPLAY". So: wait for the socket.
#   2. Don't race the service. Chromium pointed at a port nothing is
#      listening on yet shows an error page and stays there forever. So:
#      wait for the port too.
#   3. Don't let the panel blank. A hallway board that sleeps after 10
#      minutes isn't a board. swayidle is what would do the blanking.
#   4. Don't reuse the normal browser profile. A crash flag or restore-tabs
#      prompt in the everyday profile would land on the board.

URL="http://localhost:8000/display.html"
RUNTIME="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# 1. Wayland socket — ~30s of grace.
i=0
while [ "$i" -lt 60 ]; do
    [ -S "$RUNTIME/${WAYLAND_DISPLAY:-wayland-0}" ] && break
    i=$((i + 1))
    sleep 0.5
done

pkill -x swayidle 2>/dev/null
wlopm --on '*' 2>/dev/null

# 2. The service — ~30s, then launch anyway: a visible error beats a black
# screen with no clue why.
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
