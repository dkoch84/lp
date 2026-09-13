"""Tests for lp-deck's now-playing plumbing: the vinyl, the queue list and
track lookups.

Slow paths found by comparing with mature players: the vinyl rebuilt itself
(with pygame, on the window's thread) on every now-playing change, including a
heart being tapped; the queue list reset entirely on each track change, losing
its scroll position; queuing a list of paths ran one query per path; and the
now-playing title was re-read from the file's tags even though the library
already had it.

    .venv/bin/python -m pytest tests/test_lpdeck_now_playing.py
"""
import os
import sys
import threading
import time

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip('PySide6', reason='lp-deck needs PySide6 (requirements-deck.txt)')

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage

from lpcore.vinyl.settings import VinylSettings
from lpdeck import db, qmlapp, vinyl_item


@pytest.fixture(scope='module')
def app():
    return QGuiApplication.instance() or QGuiApplication([])


def _wait(app, predicate, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# --- the vinyl ----------------------------------------------------------------------

class _Backend:
    track_boundaries = [0.0, 100.0]
    album_duration = 200.0

    def get_status(self):
        return {"playing": True}


class _Controller(QObject):
    nowPlayingChanged = Signal()
    vinylChanged = Signal()

    def __init__(self):
        super().__init__()
        self.player = type("P", (), {"backend": _Backend()})()
        self.settings = VinylSettings(style="black")

    def vinyl_now(self):
        return {"album_path": "/music/A/Album", "art_path": None, "artist": "A",
                "album": "Album", "settings": self.settings}


@pytest.fixture
def renders(monkeypatch):
    calls = []

    def fake_composite(renderer, size, boundaries, dur, art, album_path, artist, album,
                       with_shine=True, delay=0.0):
        calls.append(renderer.settings.to_dict())
        time.sleep(fake_composite.delay)
        img = QImage(8, 8, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.white)
        return img, img
    fake_composite.delay = 0.0
    monkeypatch.setattr(vinyl_item, "composite_disc", fake_composite)
    return calls, fake_composite


def test_unchanged_now_playing_does_not_rerender_the_vinyl(app, renders):
    calls, _fake = renders
    c = _Controller()
    item = vinyl_item.VinylItem()
    item.setController(c)
    assert _wait(app, lambda: item._disc is not None)
    assert len(calls) == 1
    for _ in range(3):                       # e.g. a heart tapped, the queue footer ticking
        c.nowPlayingChanged.emit()
    app.processEvents()
    assert len(calls) == 1


def test_a_changed_look_rerenders(app, renders):
    calls, _fake = renders
    c = _Controller()
    item = vinyl_item.VinylItem()
    item.setController(c)
    assert _wait(app, lambda: len(calls) == 1 and item._disc is not None)
    c.settings = VinylSettings(style="black", effects=["glass"])
    c.vinylChanged.emit()
    assert _wait(app, lambda: len(calls) == 2)


def test_the_render_does_not_block_the_window(app, renders):
    calls, fake = renders
    fake.delay = 0.6
    c = _Controller()
    item = vinyl_item.VinylItem()
    started = time.monotonic()
    item.setController(c)
    assert time.monotonic() - started < 0.3, "the render ran on the calling thread"
    assert item._disc is None
    assert _wait(app, lambda: item._disc is not None)


def test_a_stale_render_is_dropped(app, renders):
    _calls, _fake = renders
    item = vinyl_item.VinylItem()
    old = QImage(4, 4, QImage.Format_ARGB32_Premultiplied)
    item._generation = 2
    item._on_rendered(1, old, old)
    assert item._disc is None


# --- queue list and lookups ------------------------------------------------------------------

class _Player:
    def __init__(self, queue):
        self.queue = queue
        self.index = 0


def _row(path):
    return {"path": path, "title": os.path.basename(path)}


def test_track_change_updates_rows_instead_of_resetting(app):
    player = _Player([_row("/a"), _row("/b"), _row("/c")])
    model = qmlapp.QueueModel(player)
    model.reload()
    resets, changed = [], []
    model.modelReset.connect(lambda: resets.append(1))
    model.dataChanged.connect(lambda tl, br, roles: changed.append(tl.row()))
    player.index = 2
    model.reload()
    assert resets == [] and sorted(changed) == [0, 2]
    player.queue = player.queue + [_row("/d")]
    model.reload()
    assert resets == [1]


@pytest.fixture
def controller(tmp_path):
    from lpdeck.shot import _FakeBackend, _FakePlayer
    app = QGuiApplication.instance() or QGuiApplication([])
    con = db.connect(str(tmp_path / "library.db"))
    aid = con.execute("INSERT INTO artists(name, sort_name) VALUES ('Artist', 'artist')").lastrowid
    alid = con.execute("INSERT INTO albums(artist_id, name, path) VALUES (?, 'Album', '/music/Artist/Album')",
                       (aid,)).lastrowid
    for n in (1, 2, 3):
        con.execute("INSERT INTO tracks(album_id, artist_id, title, track_no, path, duration) "
                    "VALUES (?,?,?,?,?,?)", (alid, aid, f"Song {n}", n,
                                             f"/music/Artist/Album/{n}.flac", 100.0 + n))
    con.commit()
    player = _FakePlayer(_FakeBackend(con))
    c = qmlapp.Controller(con, player, qmlapp.ArtistsModel(con), qmlapp.QueueModel(player))
    yield app, c, player
    con.close()


def test_path_lookups_keep_order_and_drop_unknown_paths(controller):
    _app, c, _player = controller
    got = c._track_dicts_for_paths(["/music/Artist/Album/3.flac", "/nope.flac",
                                    "/music/Artist/Album/1.flac"])
    assert [t["title"] for t in got] == ["Song 3", "Song 1"]
    assert got[0]["duration"] == 103.0 and got[0]["album_name"] == "Album"


def test_now_playing_title_comes_from_the_library(controller):
    _app, c, player = controller
    player.backend.playing = True            # its tags would say "Ambitionz az a Ridah"
    player.queue = c._track_dicts_for_paths(["/music/Artist/Album/2.flac"])
    player.index = 0
    c._refresh_now_playing()
    assert c.npTitle == "Song 2"
    assert c.npSub == "Artist — Album"


def test_concurrent_renders_share_one_lock():
    from lpdeck import vinyl_preview
    assert vinyl_preview._LOCK is vinyl_item.RENDER_LOCK
    assert isinstance(vinyl_item.RENDER_LOCK, type(threading.Lock()))


_DELETE_MID_RENDER = r"""
import gc, os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage
from lpcore.vinyl.settings import VinylSettings
from lpdeck import vinyl_item

app = QGuiApplication([])

def slow_composite(*args, **kwargs):
    time.sleep(0.2)
    img = QImage(8, 8, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.white)
    return img, img

vinyl_item.composite_disc = slow_composite

class Backend:
    track_boundaries = [0.0, 100.0]
    album_duration = 200.0
    def get_status(self):
        return {"playing": True}

class Controller(QObject):
    nowPlayingChanged = Signal()
    vinylChanged = Signal()
    def __init__(self):
        super().__init__()
        self.player = type("P", (), {"backend": Backend()})()
    def vinyl_now(self):
        return {"album_path": "/music/A/Album", "art_path": None, "artist": "A",
                "album": "Album", "settings": VinylSettings(style="black")}

c = Controller()
for _ in range(8):
    item = vinyl_item.VinylItem()
    item.setController(c)
    del item
    gc.collect()
    end = time.monotonic() + 0.3
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
print("survived")
"""


def test_deleting_the_vinyl_mid_render_does_not_crash(tmp_path):
    """A render finishing after its item was destroyed (a view closed mid-render)
    used to deliver into the dead object and segfault the whole app. Run in a
    subprocess so a crash fails this test instead of taking pytest down."""
    import subprocess
    script = tmp_path / "delete_mid_render.py"
    script.write_text(_DELETE_MID_RENDER)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, str(script), repo], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}: {r.stderr[-800:]}"
    assert "survived" in r.stdout
