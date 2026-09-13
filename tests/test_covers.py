"""Tests for lpcore.covers: which picture is an album's cover.

Only four exact names used to count (cover/folder, .jpg or .png), so front.jpg,
Cover.JPEG, a lone scan in the folder, and art embedded in the tracks all showed
no cover. The same lookup now serves the kiosk's library, the player's
now-playing art and lp-deck's scan.

    .venv/bin/python -m pytest tests/test_covers.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore import covers

# a 1x1 PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cfc0f01f0005fe02fe0dc3a3a50000000049454e44ae426082")


@pytest.fixture(autouse=True)
def cache_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path / "cache" / "lp" / "covers"


def _touch(folder, *names):
    folder.mkdir(parents=True, exist_ok=True)
    for n in names:
        (folder / n).write_bytes(b"x")
    return folder


def _mp3_with_art(path, data=PNG, mime="image/png", pic_type=3):
    from mutagen.id3 import APIC, ID3
    path.write_bytes(b"\x00" * 64)
    tags = ID3()
    tags.add(APIC(encoding=3, mime=mime, type=pic_type, desc="", data=data))
    tags.save(str(path))
    return str(path)


@pytest.mark.parametrize("name", ["cover.jpg", "Cover.JPEG", "folder.png", "Front.webp",
                                  "album.jpg", "AlbumArt.png"])
def test_cover_names_in_any_case_and_image_type(tmp_path, name):
    album = _touch(tmp_path / "Album", name, "01 track.flac", "notes.txt")
    assert covers.cover_file(str(album)) == str(album / name)


def test_preferred_names_win_in_order(tmp_path):
    album = _touch(tmp_path / "Album", "back.jpg", "front.jpg", "folder.jpg")
    assert covers.cover_file(str(album)) == str(album / "folder.jpg")


@pytest.mark.parametrize("files,expected", [
    (["Cover.jpg", "cover.jpg"], "cover.jpg"),
    (["cover.jpeg", "cover.jpg"], "cover.jpg"),
    (["Cover.png", "cover.jpeg"], "Cover.png"),
    (["Folder.jpg", "cover.webp"], "Folder.jpg"),
    (["cover.png", "Cover.jpg"], "cover.png"),
    (["cover.webp", "front.jpeg"], "cover.webp"),
])
def test_several_spellings_pick_what_the_original_lookup_did(tmp_path, files, expected):
    """Albums with duplicate cover files must keep the cover they always had."""
    album = _touch(tmp_path / "Album", *files)
    assert covers.cover_file(str(album)) == str(album / expected)


def test_a_lone_picture_is_the_cover(tmp_path):
    album = _touch(tmp_path / "Album", "scan-001.jpg", "01 track.flac")
    assert covers.cover_file(str(album)) == str(album / "scan-001.jpg")


def test_several_unnamed_pictures_are_not_guessed(tmp_path):
    album = _touch(tmp_path / "Album", "scan-001.jpg", "scan-002.jpg")
    assert covers.cover_file(str(album)) is None


def test_no_pictures_or_no_folder(tmp_path):
    assert covers.cover_file(str(_touch(tmp_path / "Album", "01.flac"))) is None
    assert covers.cover_file(str(tmp_path / "nope")) is None


def test_embedded_art_is_extracted_and_cached(tmp_path, cache_home, monkeypatch):
    track = _mp3_with_art(tmp_path / "01 track.mp3")
    first = covers.embedded_cover(track)
    assert first and first.startswith(str(cache_home)) and first.endswith(".png")
    assert open(first, "rb").read() == PNG
    reads = []
    real = covers._pictures
    monkeypatch.setattr(covers, "_pictures", lambda p: reads.append(p) or real(p))
    assert covers.embedded_cover(track) == first
    assert reads == []                       # the second call didn't open the track


def test_front_cover_is_preferred_over_other_pictures(tmp_path):
    from mutagen.id3 import APIC, ID3
    track = tmp_path / "t.mp3"
    track.write_bytes(b"\x00" * 64)
    tags = ID3()
    tags.add(APIC(encoding=3, mime="image/jpeg", type=4, desc="back", data=b"BACK"))
    tags.add(APIC(encoding=3, mime="image/png", type=3, desc="front", data=PNG))
    tags.save(str(track))
    assert open(covers.embedded_cover(str(track)), "rb").read() == PNG


def test_a_track_without_art_is_remembered(tmp_path, monkeypatch):
    track = tmp_path / "plain.mp3"
    track.write_bytes(b"\x00" * 64)
    assert covers.embedded_cover(str(track)) is None
    monkeypatch.setattr(covers, "_pictures", lambda p: pytest.fail("re-read a track with no art"))
    assert covers.embedded_cover(str(track)) is None


def test_a_changed_track_is_read_again(tmp_path):
    track = tmp_path / "t.mp3"
    _mp3_with_art(track)
    first = covers.embedded_cover(str(track))
    _mp3_with_art(track, data=PNG + b"changed")
    os.utime(track, (1, 1))
    second = covers.embedded_cover(str(track))
    assert second != first and open(second, "rb").read().endswith(b"changed")


def test_find_cover_prefers_a_folder_picture_over_embedded_art(tmp_path):
    album = tmp_path / "Album"
    album.mkdir()
    track = _mp3_with_art(album / "01.mp3")
    assert covers.find_cover(str(album), [track]).endswith(".png")      # embedded
    (album / "cover.jpg").write_bytes(b"x")
    assert covers.find_cover(str(album), [track]) == str(album / "cover.jpg")


def test_the_kiosk_library_shows_embedded_art(tmp_path):
    from lpcore.library import Library
    album = tmp_path / "Artist" / "1996 - Album"
    album.mkdir(parents=True)
    _mp3_with_art(album / "01 One.mp3")
    lib = Library(str(tmp_path))
    found = lib.get_album_by_path(str(album))
    assert found.cover_path and found.cover_path.endswith(".png")
    assert (found.year, found.display_name) == ("1996", "Album")
