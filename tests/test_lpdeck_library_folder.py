"""Tests for lp-deck's music library folder setting.

Settings lets you pick the library folder. Picking one must scan it on a
background thread (so the window stays usable), fill an empty artist list as
it goes, and drop albums that belonged to the old folder. A second request
made while a scan is running must not be lost or run two scans at once.

QSettings is pointed at a temporary directory, so these never touch your real
lp-deck settings.

    .venv/bin/python -m pytest tests/test_lpdeck_library_folder.py
"""
import os
import sys
import time

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip('PySide6', reason='lp-deck needs PySide6 (requirements-deck.txt)')
pytest.importorskip('mutagen')

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QGuiApplication

from lpdeck import db, qmlapp
from lpdeck.shot import _FakeBackend, _FakePlayer


def _album(root, artist, album, tracks=("01 One.mp3", "02 Two.mp3")):
    d = root / artist / album
    d.mkdir(parents=True)
    for t in tracks:
        (d / t).write_bytes(b"")
    return d


def _wait(app, predicate, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    app.processEvents()
    return predicate()


@pytest.fixture
def deck(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / "settings"))
    app = QGuiApplication.instance() or QGuiApplication([])
    app.setOrganizationName("lp-deck-test")
    app.setApplicationName("lp-deck-test")

    db_path = str(tmp_path / "library.db")
    con = db.connect(db_path)
    player = _FakePlayer(_FakeBackend(con))
    artists = qmlapp.ArtistsModel(con)
    controller = qmlapp.Controller(con, player, artists, qmlapp.QueueModel(player))
    controller.db_path = db_path
    yield app, controller, con, artists
    con.close()


def _idle(controller):
    return not controller.scanning and controller._scan_pending is None


def _artist_names(con):
    return sorted(r["name"] for r in con.execute("SELECT name FROM artists"))


def test_startup_scan_fills_the_empty_library(deck, tmp_path):
    app, c, con, artists = deck
    music = tmp_path / "music"
    _album(music, "Artist A", "Album One")
    _album(music, "Artist B", "Album Two")
    c.use_music_folder(str(music))
    c.start_index(str(music))
    assert c.scanning and c.scanStatus.startswith("Scanning")
    assert _wait(app, lambda: _idle(c))
    assert artists.rowCount() == 2
    assert c.scanStatus == "2 artists, 2 albums, 4 tracks"


def test_choosing_a_folder_switches_the_library_and_drops_the_old_one(deck, tmp_path):
    app, c, con, artists = deck
    old, new = tmp_path / "old", tmp_path / "new"
    _album(old, "Old Artist", "Old Album")
    _album(new, "New Artist", "New Album")
    c.use_music_folder(str(old))
    c.start_index(str(old))
    assert _wait(app, lambda: _idle(c))
    assert _artist_names(con) == ["Old Artist"]

    c.setMusicFolder(QUrl.fromLocalFile(str(new)))      # what the folder dialog hands over
    assert c.musicFolder == str(new)
    assert _wait(app, lambda: _idle(c))
    assert _artist_names(con) == ["New Artist"]
    assert artists.rowCount() == 1
    assert QSettings().value("musicFolder") == str(new)  # remembered for next launch


def test_a_missing_folder_changes_nothing(deck, tmp_path):
    app, c, con, _artists = deck
    music = tmp_path / "music"
    _album(music, "Artist A", "Album One")
    c.use_music_folder(str(music))
    c.setMusicFolder(str(tmp_path / "does-not-exist"))
    assert c.musicFolder == str(music)
    assert c.scanStatus.startswith("Folder not found")
    assert not c.scanning


def test_a_folder_picked_mid_scan_is_queued_and_wins(deck, tmp_path):
    app, c, con, _artists = deck
    first, second = tmp_path / "first", tmp_path / "second"
    for i in range(20):
        _album(first, f"First {i:02d}", "Album")
    _album(second, "Second", "Album")
    c.use_music_folder(str(first))
    c.start_index(str(first))
    c.setMusicFolder(str(second))                        # arrives while the first scan runs
    assert _wait(app, lambda: _idle(c), timeout=60)
    assert _artist_names(con) == ["Second"]


def test_a_folder_change_on_disk_starts_a_quick_scan(deck, tmp_path, monkeypatch):
    app, c, con, _artists = deck
    music = tmp_path / "music"
    _album(music, "Artist A", "Album One")
    c.use_music_folder(str(music))
    calls = []
    monkeypatch.setattr(c, "start_index", lambda path, quick=False: calls.append((path, quick)))
    c._on_library_dir_changed(str(music))
    c._on_library_dir_changed(str(music))            # a burst of changes: one scan
    assert c._watch_timer.isActive() and calls == []
    c._on_watch_timer()
    assert calls == [(str(music), True)]


def test_watches_cover_the_folder_its_artists_and_albums(deck, tmp_path):
    app, c, con, _artists = deck
    music = tmp_path / "music"
    _album(music, "Artist A", "Album One")
    _album(music, "Artist B", "Album Two")
    c.use_music_folder(str(music))
    c.start_index(str(music))
    assert _wait(app, lambda: _idle(c))
    assert _wait(app, lambda: not c._watch_queue)
    watched = set(c._watcher.directories())
    assert {str(music), str(music / "Artist A"), str(music / "Artist A" / "Album One"),
            str(music / "Artist B" / "Album Two")} <= watched


def test_a_full_request_wins_over_a_queued_quick_one(deck, tmp_path):
    app, c, con, _artists = deck
    music = tmp_path / "music"
    for i in range(10):
        _album(music, f"Artist {i}", "Album")
    c.use_music_folder(str(music))
    c.start_index(str(music), quick=True)
    c.start_index(str(music), quick=True)
    c.start_index(str(music))                         # full
    assert c._scan_pending == (str(music), False)
    assert _wait(app, lambda: _idle(c), timeout=60)
