"""Entry point: python -m lpdeck

Wires SQLite + lpcore + the Qt window. Config (music path, lastfm) is read from
the same config.yml the kiosk uses, by default.
"""
import os
import sys

import yaml

from lpcore.player import PlayerBackend
from lpcore.scrobbler import Scrobbler
from . import db
from .player import QueuePlayer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "lp-deck")


def _load_config():
    for p in ("config.yml", os.path.expanduser("~/.config/lp/config.yml")):
        if os.path.isfile(p):
            with open(p) as f:
                return yaml.safe_load(f) or {}
    return {}


def main():
    from PySide6.QtWidgets import QApplication
    from .app import MainWindow

    config = _load_config()
    con = db.connect(os.path.join(DATA_DIR, "library.db"))

    backend = PlayerBackend(audio_output=config.get("audio_output", "alsa"))
    scrobbler = Scrobbler(backend, config.get("lastfm", {}))   # req #9
    player = QueuePlayer(backend, scrobbler)

    app = QApplication(sys.argv)
    win = MainWindow(con, player)
    win.show()
    try:
        sys.exit(app.exec())
    finally:
        player.shutdown()


if __name__ == "__main__":
    main()
