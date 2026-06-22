"""Entry point: python -m lpdeck

Wires SQLite + lpcore + the Qt window. Config (music path, lastfm) is read from
the same config.yml the kiosk uses, by default.
"""
import os
import sys
import threading

import yaml

from lpcore.player import PlayerBackend
from lpcore.scrobbler import Scrobbler
from . import db, indexer
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
    from . import theme

    config = _load_config()
    music_path = config.get("music_library_path", "/mnt/share/media/Music")
    db_path = os.path.join(DATA_DIR, "library.db")
    con = db.connect(db_path)

    backend = PlayerBackend(audio_output=config.get("audio_output", "alsa"))
    scrobbler = Scrobbler(backend, config.get("lastfm", {}))   # req #9
    player = QueuePlayer(backend, scrobbler)

    app = QApplication(sys.argv)
    theme.apply(app)            # minimalist polish over the inherited qt6ct/Plasma theme
    win = MainWindow(con, player)
    win.show()

    # Index the library in the background (own connection — sqlite isn't shared
    # across threads), then refresh the view via the queued signal.
    def reindex():
        c = db.connect(db_path)
        indexer.index_library(c, music_path)
        c.close()
        win.library_indexed.emit()
    threading.Thread(target=reindex, daemon=True).start()

    try:
        sys.exit(app.exec())
    finally:
        player.shutdown()


if __name__ == "__main__":
    main()
