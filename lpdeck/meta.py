"""Read/write track tags via mutagen — backs the "Edit Metadata" form (req #2).

`mutagen.File(..., easy=True)` gives a uniform title/artist/album/tracknumber
mapping across MP3/FLAC/…, so the editor doesn't care about the container.
"""
import os

from mutagen import File as MutagenFile


def read(path):
    """{title, artist, album, track} for `path` (blanks on failure)."""
    blank = {"title": "", "artist": "", "album": "", "track": ""}
    try:
        a = MutagenFile(path, easy=True)
    except Exception:
        a = None
    if a is None:
        blank["title"] = os.path.splitext(os.path.basename(path))[0]
        return blank

    def g(k):
        return (a.get(k) or [""])[0]

    return {"title": g("title") or os.path.splitext(os.path.basename(path))[0],
            "artist": g("artist"), "album": g("album"),
            "track": g("tracknumber")}


def write(path, title=None, artist=None, album=None, track=None):
    """Apply non-None fields to `path`'s tags. Returns True on success."""
    try:
        a = MutagenFile(path, easy=True)
        if a is None:
            return False
        if title is not None:
            a["title"] = title
        if artist is not None:
            a["artist"] = artist
        if album is not None:
            a["album"] = album
        if track is not None:
            a["tracknumber"] = str(track)
        a.save()
        return True
    except Exception:
        return False
