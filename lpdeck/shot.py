"""Headless QML screenshot harness — fast "devtools" for lp-deck's UI.

Renders the REAL `qml/Main.qml` to a PNG without needing a display, driven by a
fake now-playing state, so layouts / popups / the vinyl can be eyeballed in
seconds (the same harness used to develop the UI). QML warnings are printed,
with the teardown-time "controller is null" GC noise filtered out.

    python -m lpdeck.shot out.png [--play] [--expand] [--vinyl] [--queue]
                                  [--w 1320] [--h 900] [--wait 1500]

For inspecting a LIVE window instead (full object/property/binding tree, the
real Qt equivalent of browser devtools), use GammaRay — see the README.
"""
import argparse
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtQuickControls2 import QQuickStyle

from . import db, qmlapp
from .vinyl_item import VinylItem

DB_PATH = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "lp-deck", "library.db")


class _FakeBackend:
    """A no-audio backend reporting a fixed now-playing album from the library."""
    def __init__(self, con):
        row = con.execute(
            "SELECT id, name, path, cover_path, artist_id FROM albums "
            "WHERE cover_path IS NOT NULL LIMIT 1").fetchone()
        self.album_id = row["id"] if row else -1
        self.artist_id = row["artist_id"] if row else -1
        self.album_path = row["path"] if row else None
        self._cover = row["cover_path"] if row else None
        self._album = row["name"] if row else ""
        self._artist = (con.execute("SELECT name FROM artists WHERE id=?",
                        (self.artist_id,)).fetchone()["name"]) if row else ""
        self.track_boundaries = [0, 80, 170, 290]
        self.album_duration = 290.0
        self.playing = False

    def on(self, ev, cb):
        pass

    def get_status(self):
        if not self.playing:
            return {"playing": False}
        return {"playing": True, "artist": self._artist, "album": self._album,
                "track_title": "Ambitionz az a Ridah",
                "progress": {"album_duration": self.album_duration, "elapsed": 104.0}}

    def find_album_art(self, path):
        return self._cover

    # transport extras (seek / volume / mute / pause-state)
    def set_volume(self, v): self._vol = v
    def get_volume(self): return getattr(self, "_vol", 100)
    def is_muted(self): return False
    def toggle_mute(self): pass
    def is_actively_playing(self): return self.playing
    def seek_fraction(self, f): pass
    def get_current_time(self): return 104.0
    def set_crossfade(self, ms): self._xf = ms
    def set_equalizer(self, enabled, preamp=0.0, bands=None): pass
    def eq_bands(self): return [31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
    fade_ms = 0
    def output_devices(self): return [("speakers", "Built-in speakers"), ("hdmi", "HDMI")]
    def set_output_device(self, device_id): self._device = device_id


class _FakePlayer:
    def __init__(self, backend):
        self.backend = backend
        self.index = 0
        self.queue = []
        self.shuffle = False
        self.repeat = "off"

    def toggle(self): pass
    def next(self): pass
    def previous(self): pass
    def jump_to(self, i): pass
    def set_queue(self, tracks, start=0, album_path=None):
        self.queue = list(tracks); self.index = start
    def add_tracks(self, tracks, play_next=False): self.queue.extend(tracks)
    def set_shuffle(self, on): self.shuffle = on
    def set_repeat(self, m): self.repeat = m
    def cycle_repeat(self): return self.repeat
    def set_volume(self, v): self.backend.set_volume(v)
    def get_volume(self): return self.backend.get_volume()
    def toggle_mute(self): pass
    def seek(self, f): pass
    def current(self): return None


def _pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main():
    ap = argparse.ArgumentParser(description="Headless lp-deck QML screenshot")
    ap.add_argument("out", help="output PNG path")
    ap.add_argument("--play", action="store_true", help="simulate an album playing")
    ap.add_argument("--expand", action="store_true", help="open the expanded view")
    ap.add_argument("--vinyl", action="store_true", help="open the vinyl config")
    ap.add_argument("--queue", action="store_true", help="open the queue panel")
    ap.add_argument("--w", type=int, default=1320)
    ap.add_argument("--h", type=int, default=900)
    ap.add_argument("--wait", type=int, default=1800,
                    help="ms to settle (raise for many async tiles)")
    args = ap.parse_args()

    QGuiApplication.setOrganizationName("lp-deck")
    QGuiApplication.setApplicationName("lp-deck")
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)   # also keeps the instance referenced
    qmlRegisterType(VinylItem, "Lpdeck", 1, 0, "VinylItem")

    con = db.connect(DB_PATH)
    backend = _FakeBackend(con)
    player = _FakePlayer(backend)
    artists = qmlapp.ArtistsModel(con)
    queue = qmlapp.QueueModel(player)
    controller = qmlapp.Controller(con, player, artists, queue)

    engine = QQmlApplicationEngine()
    engine.addImageProvider("tiles", qmlapp.TileProvider(DB_PATH))
    engine.addImageProvider("vinyl", qmlapp.VinylPreviewProvider(DB_PATH))
    ctx = engine.rootContext()
    ctx.setContextProperty("artistsModel", artists)
    ctx.setContextProperty("queueModel", queue)
    ctx.setContextProperty("controller", controller)

    warnings = []
    engine.warnings.connect(
        lambda ws: warnings.extend(str(w.toString()) for w in ws))
    engine.load(os.path.join(qmlapp.QML_DIR, "Main.qml"))
    roots = engine.rootObjects()
    if not roots:
        print("LOAD FAILED:", file=sys.stderr)
        for w in warnings:
            print(" ", w, file=sys.stderr)
        sys.exit(1)
    win = roots[0]
    win.setWidth(args.w)
    win.setHeight(args.h)

    if args.play:
        backend.playing = True
        controller._np_album_id = backend.album_id
        controller._np_artist_id = backend.artist_id
        controller._refresh_now_playing()
    if args.queue:
        win.setProperty("queueOpen", True)
    if args.expand:
        win.setProperty("expanded", True)
    if args.vinyl:
        win.setProperty("vinylConfig", True)

    _pump(args.wait)
    win.grabWindow().save(args.out)

    # surface only real warnings (drop teardown "... is null" GC noise)
    real = [w for w in warnings if "of null" not in w and "is null" not in w]
    print(f"saved {args.out}  ({len(real)} warning(s))")
    for w in real:
        print(" ", w)


if __name__ == "__main__":
    main()
