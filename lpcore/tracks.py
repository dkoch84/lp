"""The one place that decides which files in an album folder are tracks, and
what order they go in.

Both the library (what the web UI lists) and the player (what actually gets
queued) read an album directory themselves. When those two disagree, by even one
file, an index into the listing stops meaning the track it looked like: the
track picker sends row N and the player starts something else. They had drifted
in both directions at once, so this module exists to make that impossible:

  * MEMBERSHIP. The library counted only .mp3/.flac while the player queued
    eleven formats, so one .m4a in a folder shifted every index after it.
  * ORDER. Both sorted filenames as plain strings, which puts an unpadded
    album in the order 1, 10, 11, 2, 3 — wrong in the listing, and wrong in
    the actual playback order, which is the part that matters.
"""
import os
import re

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.aac', '.ogg', '.oga',
                    '.opus', '.wav', '.wma', '.aiff', '.aif')

_DIGITS = re.compile(r'(\d+)')


def natural_key(name):
    """Sort key ordering embedded numbers by value: 2 before 10.

    Splits into digit and non-digit runs and compares the digit runs as ints, so
    "2 - Stasis.flac" sorts before "10 - Caledonia.flac" the way a track listing
    on a sleeve does. Non-digit runs are compared case-insensitively, so a
    folder of mixed-case names does not order by ASCII.

    Leading zeros do not change the value, so a folder mixing "03" and "3"
    still lands in the right place. The tuple is (is_text, value) per run so
    ints and strings are never compared against each other, which would raise.
    """
    parts = _DIGITS.split(name)
    key = []
    for i, part in enumerate(parts):
        if i % 2:                       # split() puts the digit runs at odd i
            key.append((0, int(part), ''))
        elif part:
            key.append((1, 0, part.lower()))
    return key


def is_audio(name):
    return name.lower().endswith(AUDIO_EXTENSIONS)


def album_track_names(album_path):
    """The album's track filenames, in play order. [] if it is not a directory.

    Used for anything that lists or counts tracks. album_track_paths() returns
    the same files as full paths, in the same order, for anything that plays
    them; index N means the same track in both.
    """
    try:
        names = os.listdir(album_path)
    except OSError:                     # missing, unreadable, or not a dir
        return []
    return sorted((f for f in names if is_audio(f)), key=natural_key)


def album_track_paths(album_path):
    """album_track_names(), joined onto `album_path`."""
    return [os.path.join(album_path, f) for f in album_track_names(album_path)]
