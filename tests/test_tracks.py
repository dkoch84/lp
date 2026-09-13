"""Tests for lpcore.tracks: which files are an album's tracks, and their order.

The point: the library lists tracks and the player queues them, from separate
readings of the same directory. Row N in the web UI is sent back as a start
index into the player's list, so if those two readings ever disagree about
membership OR order, the picker starts the wrong track. Both had drifted:

  * the library counted .mp3/.flac while the player queued eleven formats, so a
    single .m4a shifted every index after it;
  * both sorted filenames as plain text, so an unpadded album ran 1, 10, 11, 2:
    not just displayed that way, PLAYED that way.

So the ordering tests below matter, and the agreement tests at the bottom matter
more: they are the invariant the track picker rests on.

    .venv/bin/python -m pytest tests/test_tracks.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.tracks import (AUDIO_EXTENSIONS, album_track_names,
                           album_track_paths, is_audio, natural_key)


def _album(tmp_path, names):
    d = tmp_path / "album"
    d.mkdir(exist_ok=True)
    for n in names:
        (d / n).write_bytes(b"")
    return str(d)


# --- ordering --------------------------------------------------------------

def test_unpadded_track_numbers_sort_by_value(tmp_path):
    """The reported bug: 1, 10, 2, 3 in both the listing and the play order."""
    names = [f"{i} Track.flac" for i in (1, 2, 3, 9, 10, 11, 20)]
    path = _album(tmp_path, names)
    assert album_track_names(path) == names


def test_zero_padded_still_sorts_correctly(tmp_path):
    names = [f"{i:02d} Track.flac" for i in range(1, 13)]
    path = _album(tmp_path, names)
    assert album_track_names(path) == names


def test_mixed_padding_sorts_by_value(tmp_path):
    """A folder half-retagged: leading zeros must not change the value."""
    path = _album(tmp_path, ["01 A.flac", "2 B.flac", "003 C.flac", "10 D.flac"])
    assert album_track_names(path) == ["01 A.flac", "2 B.flac", "003 C.flac",
                                       "10 D.flac"]


@pytest.mark.parametrize("names,expected", [
    (["1-01 A.flac", "1-02 B.flac", "2-01 C.flac"],
     ["1-01 A.flac", "1-02 B.flac", "2-01 C.flac"]),
    (["Disc 1 - 2 B.flac", "Disc 1 - 10 C.flac", "Disc 2 - 1 A.flac"],
     ["Disc 1 - 2 B.flac", "Disc 1 - 10 C.flac", "Disc 2 - 1 A.flac"]),
])
def test_multi_disc_naming_orders_by_each_number_in_turn(tmp_path, names, expected):
    assert album_track_names(_album(tmp_path, names)) == expected


def test_names_without_numbers_sort_case_insensitively(tmp_path):
    """Plain ASCII sort would put every capital before every lowercase."""
    path = _album(tmp_path, ["apple.flac", "Banana.flac", "cherry.flac"])
    assert album_track_names(path) == ["apple.flac", "Banana.flac", "cherry.flac"]


def test_numbers_sort_before_text_consistently(tmp_path):
    path = _album(tmp_path, ["1 A.flac", "Intro.flac", "2 B.flac"])
    got = album_track_names(path)
    assert got.index("1 A.flac") < got.index("2 B.flac")
    assert len(got) == 3


def test_natural_key_never_compares_int_to_str():
    """The classic crash in a hand-rolled natural sort: a name that starts with
    a digit against one that does not."""
    names = ["10 a", "b", "3 c", "d 4", "5"]
    sorted(names, key=natural_key)          # must not raise


def test_very_long_numbers_do_not_overflow_the_key():
    assert natural_key("9" * 40 + ".flac") > natural_key("8" * 40 + ".flac")


# --- membership ------------------------------------------------------------

def test_every_declared_extension_is_recognised(tmp_path):
    names = [f"1 track{ext}" for ext in AUDIO_EXTENSIONS]
    assert len(album_track_names(_album(tmp_path, names))) == len(AUDIO_EXTENSIONS)


def test_extension_matching_is_case_insensitive(tmp_path):
    path = _album(tmp_path, ["1 A.FLAC", "2 B.Mp3"])
    assert album_track_names(path) == ["1 A.FLAC", "2 B.Mp3"]


def test_non_audio_files_are_ignored(tmp_path):
    path = _album(tmp_path, ["1 A.flac", "cover.jpg", "notes.txt", "album.log"])
    assert album_track_names(path) == ["1 A.flac"]


def test_missing_directory_is_empty_not_an_error(tmp_path):
    assert album_track_names(str(tmp_path / "nope")) == []
    assert album_track_paths(str(tmp_path / "nope")) == []


def test_a_file_where_a_directory_was_expected_is_empty(tmp_path):
    f = tmp_path / "notadir"
    f.write_bytes(b"")
    assert album_track_names(str(f)) == []


def test_is_audio():
    assert is_audio("x.flac") and is_audio("X.MP3") and is_audio("y.opus")
    assert not is_audio("cover.jpg") and not is_audio("flac") and not is_audio("")


def test_paths_are_names_joined_onto_the_album(tmp_path):
    path = _album(tmp_path, ["2 B.flac", "1 A.flac"])
    assert album_track_paths(path) == [os.path.join(path, n)
                                       for n in album_track_names(path)]


# --- the invariant the track picker depends on -----------------------------

MIXED = ["1 One.flac", "2 Two.m4a", "3 Three.mp3", "4 Four.opus",
         "10 Ten.flac", "11 Eleven.ogg", "cover.jpg", "info.txt"]


def test_library_listing_and_player_queue_agree(tmp_path):
    """Library.get_album_tracks and PlayerBackend.play_album read the directory
    separately. Row N of the listing is sent back as a start index into the
    player's queue, so the two must match file for file, in order.

    This is the regression: the library saw 4 of these files and the player
    queued 6, so picking "10 Ten" played something else entirely.
    """
    from lpcore.library import Library

    lib_root = tmp_path / "music" / "Artist" / "Album"
    lib_root.mkdir(parents=True)
    for n in MIXED:
        (lib_root / n).write_bytes(b"")

    library = Library(str(tmp_path / "music"))
    listed = library.get_album_tracks(str(lib_root))
    queued = album_track_paths(str(lib_root))       # what play_album queues

    assert listed == [os.path.basename(p) for p in queued]
    assert listed == ["1 One.flac", "2 Two.m4a", "3 Three.mp3", "4 Four.opus",
                      "10 Ten.flac", "11 Eleven.ogg"]


def test_library_track_count_matches_the_listing(tmp_path):
    """The count shown on an album tile is computed by a third code path."""
    from lpcore.library import Library

    lib_root = tmp_path / "music" / "Artist" / "Album"
    lib_root.mkdir(parents=True)
    for n in MIXED:
        (lib_root / n).write_bytes(b"")

    library = Library(str(tmp_path / "music"))
    album = library.get_album_by_path(str(lib_root))
    assert album is not None
    assert album.track_count == len(library.get_album_tracks(str(lib_root)))


def test_start_index_selects_the_track_the_listing_showed(tmp_path):
    """End to end for the picker's contract, without a player: the index the UI
    sends addresses the file the user tapped."""
    from lpcore.library import Library

    lib_root = tmp_path / "music" / "Artist" / "Album"
    lib_root.mkdir(parents=True)
    for n in MIXED:
        (lib_root / n).write_bytes(b"")

    library = Library(str(tmp_path / "music"))
    listed = library.get_album_tracks(str(lib_root))
    queued = album_track_paths(str(lib_root))

    for i, name in enumerate(listed):
        assert os.path.basename(queued[i]) == name
