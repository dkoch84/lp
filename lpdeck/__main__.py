"""Entry point: python -m lpdeck

Wires SQLite + lpcore + the Qt window. Config (music path, lastfm) is read from
the same config.yml the kiosk uses, by default.
"""
import json
import os
import sys

import yaml

from lpcore.player import PlayerBackend
from lpcore.scrobbler import Scrobbler
from . import db, mpris
from .player import QueuePlayer, drop_missing

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "lp-deck")
STATE_PATH = os.path.join(DATA_DIR, "session.json")


def _restore_session(player):
    """Reload the last session's queue, paused where we left off."""
    try:
        with open(STATE_PATH) as f:
            st = json.load(f)
    except (OSError, ValueError):
        return
    if st.get("repeat"):
        player.set_repeat(st["repeat"])
    player.shuffle = bool(st.get("shuffle"))
    queue, index, offset, dropped = drop_missing(
        st.get("queue") or [], st.get("index", 0), st.get("offset", 0.0))
    if dropped:
        print(f"lp-deck: left {dropped} missing track(s) out of the restored queue")
    if queue:
        player.restore_queue(queue, index, offset, st.get("album_path"))


def _load_config():
    for p in ("config.yml", os.path.expanduser("~/.config/lp/config.yml")):
        if os.path.isfile(p):
            with open(p) as f:
                return yaml.safe_load(f) or {}
    return {}


def main():
    from . import qmlapp

    config = _load_config()
    music_path = config.get("music_library_path", "/mnt/share/media/Music")
    db_path = os.path.join(DATA_DIR, "library.db")
    con = db.connect(db_path)

    # ReplayGain mode is instance-level in libVLC, so it must be set before the
    # backend is built. Read the persisted UI choice directly (QSettings works
    # with an explicit org/app pair, no QApplication needed yet).
    from PySide6.QtCore import QSettings, QTimer
    rg = str(QSettings("lp-deck", "lp-deck").value("replaygainMode", "none"))
    backend = PlayerBackend(audio_output=config.get("audio_output", "alsa"),
                            replaygain=rg)
    scrobbler = Scrobbler(backend, config.get("lastfm", {}))   # req #9
    player = QueuePlayer(backend, scrobbler)

    # The library is indexed in the background once the window is up; see
    # Controller.start_index.
    mpris_handle = mpris.start_mpris(player)   # media keys / desktop controls

    def on_ready(controller):
        _restore_session(player)               # resume last session (paused)
        # Save the session as playback happens, and every 30 s for the position,
        # so a crash or kill doesn't lose it (the finally below covers clean exits).
        player.enable_autosave(STATE_PATH)
        autosave = QTimer(controller)
        autosave.setInterval(30000)
        autosave.timeout.connect(lambda: player.save_state(STATE_PATH))
        autosave.start()
        # A folder picked in Settings wins over config.yml (which the kiosk shares).
        chosen = str(QSettings("lp-deck", "lp-deck").value("musicFolder", "") or "")
        folder = chosen if chosen and os.path.isdir(chosen) else music_path
        controller.use_music_folder(folder)
        # quick: skip album folders unchanged since the last scan (Rescan does it all)
        controller.start_index(folder, quick=True)
        if mpris_handle:
            # repeat, shuffle and raise requests from the desktop update the window too
            mpris_handle.set_controls(controller.externalCommand.emit)

    try:
        sys.exit(qmlapp.run(con, player, db_path, on_ready=on_ready))
    finally:
        player.save_state(STATE_PATH)
        if mpris_handle:
            mpris_handle.stop()
        player.shutdown()


if __name__ == "__main__":
    main()
