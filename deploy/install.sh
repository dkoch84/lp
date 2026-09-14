#!/usr/bin/env bash
# lp installer: a kiosk or a desktop install from the latest GitHub release,
# with self-update from then on. No git, no root (two sudo lines are printed
# for you to run yourself where they apply).
#
#   curl -fsSL https://raw.githubusercontent.com/dkoch84/lp/master/deploy/install.sh | bash
#   curl -fsSL ... | bash -s -- --kiosk --music /mnt/music
#
# Options:
#   --kiosk        a screen wired to the box, no desktop: installs a systemd
#                  user service that starts at boot (default with no display)
#   --desktop      a desktop session: installs an app-menu entry (default when
#                  DISPLAY or WAYLAND_DISPLAY is set)
#   --music PATH   your music folder (Artist/Album layout); or set LP_MUSIC
#   --home PATH    where to install (default ~/lp, or LP_HOME)
#
# Layout it creates (see lp/update.py for how updates use it):
#   ~/lp/releases/<tag>/   ~/lp/current -> releases/<tag>   ~/lp/venv
#   ~/lp/cache (vinyl renders)   ~/lp/data (state)   ~/.config/lp/config.yml
set -euo pipefail

REPO="${LP_REPO:-dkoch84/lp}"
LP_HOME="${LP_HOME:-$HOME/lp}"
MUSIC="${LP_MUSIC:-}"
MODE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --kiosk) MODE=kiosk ;;
        --desktop) MODE=desktop ;;
        --music) MUSIC="$2"; shift ;;
        --home) LP_HOME="$2"; shift ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done
if [ -z "$MODE" ]; then
    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then MODE=desktop; else MODE=kiosk; fi
fi

say() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

say "checking the basics"
have python3 || die "python3 is required (Debian/Ubuntu: sudo apt install python3 python3-venv)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    || die "python 3.9 or newer is required"
python3 -c 'import venv, ensurepip' 2>/dev/null \
    || die "the python venv module is missing (Debian/Ubuntu: sudo apt install python3-venv)"
have curl || die "curl is required"
if ! have vlc && ! have cvlc && ! ldconfig -p 2>/dev/null | grep -q libvlc.so; then
    echo "warning: libVLC not found; lp needs it to play anything (Debian/Ubuntu: sudo apt install vlc)"
fi

say "installing the latest release into $LP_HOME"
mkdir -p "$LP_HOME/tmp"
curl -fsSL "https://raw.githubusercontent.com/$REPO/master/lp/update.py" -o "$LP_HOME/tmp/update.py"
python3 "$LP_HOME/tmp/update.py" --home "$LP_HOME" --repo "$REPO" bootstrap
CURRENT="$LP_HOME/current"
RELEASE="$(cat "$CURRENT/RELEASE")"

say "config"
CONF_DIR="$HOME/.config/lp"
CONF="$CONF_DIR/config.yml"
if [ -f "$CONF" ]; then
    echo "keeping $CONF"
else
    mkdir -p "$CONF_DIR"
    cp "$CURRENT/config.example.yml" "$CONF"
    if [ -n "$MUSIC" ]; then
        sed -i "s|^music_library_path:.*|music_library_path: $MUSIC|" "$CONF"
    fi
    # Route audio through pipewire/pulse where there is one: it is what makes
    # album playback gapless (DEPLOYMENT.md, step 4).
    if have pactl || have pipewire-pulse; then
        sed -i 's|^# audio_output: alsa|audio_output: pulse|' "$CONF"
    fi
    if [ "$MODE" = kiosk ]; then
        sed -i 's|^  fullscreen: false|  fullscreen: true|' "$CONF"
    fi
    echo "wrote $CONF"
    [ -n "$MUSIC" ] || echo "  -> set music_library_path in it before starting lp"
fi

if [ "$MODE" = desktop ]; then
    say "desktop entry"
    APPS="$HOME/.local/share/applications"
    ICONS="$HOME/.local/share/icons/hicolor/512x512/apps"
    mkdir -p "$APPS" "$ICONS"
    sed "s|@HOME@|$HOME|g; s|@LP_HOME@|$LP_HOME|g" "$CURRENT/deploy/lp.desktop" > "$APPS/lp.desktop"
    cp "$CURRENT/static/release-"*.png "$ICONS/lp.png" 2>/dev/null || true
    have update-desktop-database && update-desktop-database "$APPS" >/dev/null 2>&1 || true
    echo "installed $APPS/lp.desktop (look for 'lp' in your app menu)"
    echo
    echo "lp $RELEASE is installed. Start it from the app menu, or:"
    echo "  LP_HOME=$LP_HOME LP_CACHE_DIR=$LP_HOME/cache LP_DATA_DIR=$LP_HOME/data \\"
    echo "    $LP_HOME/venv/bin/python $CURRENT/main.py -c $CONF --open"
else
    say "systemd user service"
    UNITS="$HOME/.config/systemd/user"
    mkdir -p "$UNITS"
    cp "$CURRENT/deploy/lp.service" "$UNITS/lp.service"
    if [ "$LP_HOME" != "$HOME/lp" ]; then
        sed -i "s|%h/lp|$LP_HOME|g" "$UNITS/lp.service"
    fi
    systemctl --user daemon-reload
    systemctl --user enable lp >/dev/null
    echo "installed $UNITS/lp.service"
    echo
    echo "lp $RELEASE is installed. Two things need root, run them yourself:"
    echo
    echo "  sudo loginctl enable-linger $USER     # user services (lp, pipewire) start at boot"
    echo "  sudo usermod -aG video,render,audio $USER   # only if lp cannot open the screen/sound"
    echo
    echo "then start it:"
    echo
    echo "  systemctl --user start lp"
    echo "  journalctl --user -u lp -f"
fi

echo
echo "Updates: lp checks GitHub every few hours and installs the next release once"
echo "the current album ends; the web UI has Check now / Install now as well."
