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
AUTOSTART="$HOME/.config/labwc/autostart"
KIOSK_LINE="$REPO/deploy/kiosk.sh &"

echo "==> Building the renderer"
cd "$REPO"
npm run build

echo "==> Installing the user service"
mkdir -p "$HOME/.config/systemd/user"
cp "$REPO/deploy/flipboard.service" "$HOME/.config/systemd/user/flipboard.service"
chmod +x "$REPO/deploy/kiosk.sh"
systemctl --user daemon-reload
systemctl --user enable flipboard
systemctl --user restart flipboard

echo "==> Wiring the kiosk into labwc autostart"
mkdir -p "$(dirname "$AUTOSTART")"
touch "$AUTOSTART"
if ! grep -qF "deploy/kiosk.sh" "$AUTOSTART"; then
    echo "$KIOSK_LINE" >> "$AUTOSTART"
fi

echo
echo "Done. The board comes back on its own after a reboot."
echo "  systemctl --user status flipboard"
echo "  journalctl --user -u flipboard -f"
