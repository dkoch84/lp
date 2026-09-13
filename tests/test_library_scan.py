"""Tests for lp-deck's library scan (lpdeck.indexer.index_library).

Scans used to only add and update: a deleted file stayed listed forever, a
renamed album folder showed twice, and switching library folders deleted
playlists, favourites and play history outright. Now a vanished file is marked
missing (hidden, history kept), a new file that is the same recording takes
over its row, and quick scans skip album folders that haven't changed.

    .venv/bin/python -m pytest tests/test_library_scan.py
"""
import os
import shutil
import sys
import wave

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpdeck import db, indexer


def _wav(path, seconds):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(8000)
        w.writeframes(b"\x80" * int(seconds * 8000))
    return str(path)


def _album(root, artist, album, lengths=(1.0, 1.5, 2.0)):
    folder = root / artist / album
    return [_wav(folder / f"{i + 1:02d} Track {i + 1}.wav", s) for i, s in enumerate(lengths)]


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    c = db.connect(str(tmp_path / "library.db"))
    yield c
    c.close()


def _available(con, table="tracks"):
    return con.execute(f"SELECT COUNT(*) FROM {table} WHERE missing=0").fetchone()[0]


def _track_id(con, path):
    return con.execute("SELECT id FROM tracks WHERE path=?", (path,)).fetchone()["id"]


def test_first_scan(con, tmp_path):
    root = tmp_path / "music"
    _album(root, "Artist", "1999 - First")
    _album(root, "Artist", "2001 - Second", lengths=(1.0,))
    assert indexer.index_library(con, str(root)) == (1, 2, 4)
    row = con.execute("SELECT name, year FROM albums WHERE folder='1999 - First'").fetchone()
    assert (row["name"], row["year"]) == ("First", "1999")


def test_a_deleted_file_disappears_but_keeps_its_history(con, tmp_path):
    root = tmp_path / "music"
    tracks = _album(root, "Artist", "Album")
    indexer.index_library(con, str(root))
    loved, plain = _track_id(con, tracks[0]), _track_id(con, tracks[1])
    db.set_favorite(con, loved, True)
    os.remove(tracks[0])
    os.remove(tracks[1])
    indexer.index_library(con, str(root))
    assert con.execute("SELECT missing, favorite FROM tracks WHERE id=?", (loved,)).fetchone()[:] == (1, 1)
    assert con.execute("SELECT 1 FROM tracks WHERE id=?", (plain,)).fetchone() is None   # nothing kept: gone
    assert _available(con) == 1


def test_a_file_that_comes_back_is_the_same_track(con, tmp_path):
    root = tmp_path / "music"
    tracks = _album(root, "Artist", "Album")
    indexer.index_library(con, str(root))
    tid = _track_id(con, tracks[0])
    db.set_favorite(con, tid, True)
    saved = tmp_path / "saved.wav"
    shutil.move(tracks[0], saved)
    indexer.index_library(con, str(root))
    shutil.move(saved, tracks[0])
    indexer.index_library(con, str(root))
    assert _track_id(con, tracks[0]) == tid
    assert con.execute("SELECT missing FROM tracks WHERE id=?", (tid,)).fetchone()[0] == 0


def test_a_renamed_album_shows_once_and_keeps_playlists_favourites_and_look(con, tmp_path):
    root = tmp_path / "music"
    tracks = _album(root, "Artist", "Old Name")
    indexer.index_library(con, str(root))
    old_album = con.execute("SELECT id FROM albums").fetchone()["id"]
    tid = _track_id(con, tracks[1])
    db.set_favorite(con, tid, True)
    pl = db.create_playlist(con, "mix")
    db.append_to_playlist(con, pl, tid)
    db.record_play(con, tid, 1000.0)
    db.set_vinyl_override(con, "album", old_album, {"style": "nebula-teal-marble"})

    os.rename(root / "Artist" / "Old Name", root / "Artist" / "New Name")
    indexer.index_library(con, str(root))

    albums = con.execute("SELECT id, folder FROM albums WHERE missing=0").fetchall()
    assert [a["folder"] for a in albums] == ["New Name"]
    assert con.execute("SELECT COUNT(*) FROM albums").fetchone()[0] == 1
    new_path = str(root / "Artist" / "New Name" / os.path.basename(tracks[1]))
    assert _track_id(con, new_path) == tid                       # the same row, moved
    assert db.playlist_track_ids(con, pl) == [tid]
    assert con.execute("SELECT favorite, play_count FROM tracks WHERE id=?", (tid,)).fetchone()[:] == (1, 1)
    assert db.get_vinyl_override(con, "album", albums[0]["id"]) == {"style": "nebula-teal-marble"}


def test_switching_library_folders_keeps_user_data(con, tmp_path):
    old_root, new_root = tmp_path / "old", tmp_path / "new"
    tracks = _album(old_root, "Artist", "Album")
    _album(old_root, "Other", "Elsewhere")
    indexer.index_library(con, str(old_root))
    tid = _track_id(con, tracks[2])
    pl = db.create_playlist(con, "keep")
    db.append_to_playlist(con, pl, tid)

    shutil.copytree(old_root / "Artist", new_root / "Artist")
    shutil.rmtree(old_root)
    indexer.index_library(con, str(new_root))

    names = [r["name"] for r in con.execute("SELECT name FROM artists WHERE missing=0")]
    assert names == ["Artist"]
    assert db.playlist_track_ids(con, pl) == [tid]
    assert con.execute("SELECT path FROM tracks WHERE id=?", (tid,)).fetchone()[0].startswith(str(new_root))


def test_tracks_outside_a_new_folder_are_hidden_even_if_their_files_remain(con, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    kept = _album(first, "A", "Album")
    _album(second, "B", "Album", lengths=(3.0,))
    indexer.index_library(con, str(first))
    db.set_favorite(con, _track_id(con, kept[0]), True)
    indexer.index_library(con, str(second))
    assert [r["name"] for r in con.execute("SELECT name FROM artists WHERE missing=0")] == ["B"]
    assert con.execute("SELECT missing FROM tracks WHERE path=?", (kept[0],)).fetchone()[0] == 1


def test_an_unreachable_folder_changes_nothing(con, tmp_path):
    root = tmp_path / "music"
    _album(root, "Artist", "Album")
    indexer.index_library(con, str(root))
    with pytest.raises(OSError):
        indexer.index_library(con, str(tmp_path / "not-mounted"))
    empty = tmp_path / "empty-mount-point"
    empty.mkdir()
    with pytest.raises(OSError):
        indexer.index_library(con, str(empty))
    assert _available(con) == 3 and _available(con, "albums") == 1


def test_quick_scan_skips_unchanged_albums_and_catches_changed_ones(con, tmp_path, monkeypatch):
    root = tmp_path / "music"
    _album(root, "Artist", "Steady")
    changing = _album(root, "Artist", "Changing", lengths=(1.0,))
    indexer.index_library(con, str(root))
    listed = []
    real = indexer._entries
    monkeypatch.setattr(indexer, "_entries", lambda p: listed.append(os.path.basename(p)) or real(p))
    assert indexer.index_library(con, str(root), quick=True) == (1, 2, 4)
    assert "Steady" not in listed and "Changing" not in listed

    _wav(root / "Artist" / "Changing" / "02 Added.wav", 1.0)
    os.utime(root / "Artist" / "Changing", (5000, 5000))
    listed.clear()
    assert indexer.index_library(con, str(root), quick=True) == (1, 2, 5)
    assert "Changing" in listed and "Steady" not in listed
    assert os.path.exists(changing[0])


def test_progress_reports_per_album(con, tmp_path):
    root = tmp_path / "music"
    _album(root, "A", "One")
    _album(root, "B", "Two")
    calls = []
    indexer.index_library(con, str(root), progress=lambda *c: calls.append(c))
    assert calls[-1] == (2, 2, 6)
