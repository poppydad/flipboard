#!/bin/sh
# One-shot deploy on the Pi. Idempotent — safe to re-run after a code change
# (though for code-only changes `npm run build && systemctl --user restart
# flipboard` is enough).
#
#   cd ~/flipboard && ./deploy/install.sh
#
# Needs no root: the service is a --user unit and the kiosk hook is a line in
# the user's own labwc autostart.
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNITS="$HOME/.config/systemd/user"
AUTOSTART="$HOME/.config/labwc/autostart"

echo "==> Building the renderer"
cd "$REPO"
npm run build

echo "==> Installing the user units"
mkdir -p "$UNITS"
cp "$REPO/deploy/flipboard.service" "$UNITS/flipboard.service"
cp "$REPO/deploy/kiosk.service" "$UNITS/kiosk.service"
cp "$REPO/deploy/panel.service" "$UNITS/panel.service"
chmod +x "$REPO/deploy/kiosk.sh" "$REPO/deploy/panel.sh"

# An earlier version of this script put the kiosk in labwc's autostart. Pi OS
# never reads the user copy of that file, so the line was dead — and leaving
# it behind risks shadowing /etc/xdg/labwc/autostart (the panel and desktop)
# on any labwc build that does read it.
if [ -f "$AUTOSTART" ] && grep -qF "deploy/kiosk.sh" "$AUTOSTART"; then
    echo "    removing the stale labwc autostart hook"
    sed -i '\|deploy/kiosk.sh|d' "$AUTOSTART"
    [ -s "$AUTOSTART" ] || rm -f "$AUTOSTART"
fi

# HDMI audio: without this WirePlumber finds no usable output on the Pi's
# vc4-hdmi card and falls back to a Dummy Output sink. See the file itself.
mkdir -p "$HOME/.config/wireplumber/wireplumber.conf.d"
cp "$REPO/deploy/hdmi-audio.conf" "$HOME/.config/wireplumber/wireplumber.conf.d/50-hdmi-audio.conf"

systemctl --user daemon-reload
systemctl --user enable flipboard kiosk panel
systemctl --user restart flipboard
systemctl --user restart kiosk
systemctl --user restart panel

echo
echo "Done. The board comes back on its own after a reboot."
echo "  systemctl --user status flipboard kiosk panel"
echo "  journalctl --user -u flipboard -u kiosk -u panel -f"
