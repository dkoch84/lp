"""Tests for lpdeck.meta — the Edit Metadata read/write path.

The point: this is the only code in the project that WRITES to the user's music
files, so a regression here corrupts a library rather than a view. It also has a
blanket `except Exception: return False`, which is exactly the shape that turns
a real failure into a silent no-op, so the tests pin down which inputs are meant
to fail and which are meant to work.

Fixtures are synthesised, never taken from a real library: a handful of silent
MPEG-1 Layer III frames is enough for mutagen to identify the file and attach
tags to it.

    .venv/bin/python -m pytest tests/test_meta.py
"""
import os
import sys

import pytest
from mutagen import File as MutagenFile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpdeck import meta

# MPEG-1 Layer III, 128 kbps, 44.1 kHz: frame length 144*128000//44100 == 417.
# 0xFF 0xFB = sync + MPEG1 + LayerIII + no CRC; 0x90 = 128 kbps @ 44.1 kHz.
_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


@pytest.fixture
def mp3(tmp_path):
    """An untagged but structurally valid mp3 named `Some Song.mp3`."""
    p = tmp_path / "Some Song.mp3"
    p.write_bytes(_FRAME * 40)
    return str(p)


# --- read ------------------------------------------------------------------

def test_read_untagged_falls_back_to_the_filename(mp3):
    got = meta.read(mp3)
    assert got == {"title": "Some Song", "artist": "", "album": "", "track": ""}


def test_read_returns_tags_when_present(mp3):
    a = MutagenFile(mp3, easy=True)
    a["title"] = "Real Title"
    a["artist"] = "Real Artist"
    a["album"] = "Real Album"
    a["tracknumber"] = "4"
    a.save()

    assert meta.read(mp3) == {"title": "Real Title", "artist": "Real Artist",
                              "album": "Real Album", "track": "4"}


def test_read_missing_file_falls_back_to_the_filename(tmp_path):
    got = meta.read(str(tmp_path / "Ghost Track.mp3"))
    assert got["title"] == "Ghost Track"
    assert got["artist"] == got["album"] == got["track"] == ""


def test_read_non_audio_file_falls_back_to_the_filename(tmp_path):
    p = tmp_path / "notes.mp3"
    p.write_bytes(b"this is not audio")
    assert meta.read(str(p))["title"] == "notes"


def test_read_blank_title_tag_falls_back_to_the_filename(mp3):
    """An empty title tag should read as the filename, not as an empty row in
    the editor."""
    a = MutagenFile(mp3, easy=True)
    a["title"] = ""
    a["artist"] = "Someone"
    a.save()

    got = meta.read(mp3)
    assert got["title"] == "Some Song"
    assert got["artist"] == "Someone"


# --- write -----------------------------------------------------------------

def test_write_then_read_round_trip(mp3):
    assert meta.write(mp3, title="T", artist="A", album="Al", track=3) is True
    assert meta.read(mp3) == {"title": "T", "artist": "A", "album": "Al",
                              "track": "3"}


def test_write_creates_tags_on_a_file_that_had_none(mp3):
    """mutagen reports an untagged mp3 as falsy-but-not-None, so a truthiness
    check here would refuse to tag exactly the files most in need of it."""
    assert MutagenFile(mp3, easy=True).tags is None
    assert meta.write(mp3, title="First") is True
    assert meta.read(mp3)["title"] == "First"


def test_write_leaves_none_fields_untouched(mp3):
    meta.write(mp3, title="T", artist="A", album="Al", track=1)
    meta.write(mp3, title="New Title")

    got = meta.read(mp3)
    assert got["title"] == "New Title"
    assert got["artist"] == "A"
    assert got["album"] == "Al"
    assert got["track"] == "1"


def test_write_accepts_an_int_track_number(mp3):
    meta.write(mp3, track=7)
    assert meta.read(mp3)["track"] == "7"


def test_write_can_blank_a_field_with_an_empty_string(mp3):
    """'' is not None, so it must reach the file: clearing a field in the editor
    has to actually clear it."""
    meta.write(mp3, artist="A")
    meta.write(mp3, artist="")
    assert meta.read(mp3)["artist"] == ""


def test_write_returns_false_for_a_non_audio_file(tmp_path):
    p = tmp_path / "notes.mp3"
    p.write_bytes(b"this is not audio")
    assert meta.write(str(p), title="T") is False


def test_write_returns_false_for_a_missing_file(tmp_path):
    assert meta.write(str(tmp_path / "ghost.mp3"), title="T") is False


def test_failed_write_does_not_truncate_the_file(tmp_path):
    """A refused write must leave the bytes alone rather than half-rewriting."""
    p = tmp_path / "notes.mp3"
    p.write_bytes(b"this is not audio")
    before = p.read_bytes()
    meta.write(str(p), title="T")
    assert p.read_bytes() == before


def test_write_preserves_audio_length(mp3):
    """Tagging must not disturb the stream: the editor is not a transcoder."""
    before = MutagenFile(mp3).info.length
    meta.write(mp3, title="T", artist="A")
    assert MutagenFile(mp3).info.length == pytest.approx(before, abs=0.05)


def test_write_survives_unicode(mp3):
    meta.write(mp3, title="Björk", artist="Sigur Rós", album="Ágætis byrjun")
    assert meta.read(mp3) == {"title": "Björk", "artist": "Sigur Rós",
                              "album": "Ágætis byrjun", "track": ""}
