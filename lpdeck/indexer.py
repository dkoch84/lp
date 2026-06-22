"""Index the music library into SQLite (track-level).

Reuses lpcore.library.Library for the artist/album structure, then reads
per-track tags + duration with mutagen. Idempotent and incremental: tracks are
skipped when their mtime is unchanged, and rows are upserted (ids preserved, so
playlist references survive a reindex). Designed to run on a background thread.
"""
import os

from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3

from lpcore.library import Library


def _int(v):
    try:
        return int(str(v).split('/')[0])
    except (TypeError, ValueError):
        return 0


def read_tags(path):
    """(title, track_no, disc_no, duration) — title falls back to the filename."""
    title = track = disc = None
    dur = 0.0
    try:
        low = path.lower()
        if low.endswith('.flac'):
            a = FLAC(path)
            dur = a.info.length
        elif low.endswith('.mp3'):
            dur = MP3(path).info.length
            try:
                a = EasyID3(path)
            except Exception:
                a = {}
        else:
            a = {}
        title = (a.get('title') or [None])[0]
        track = (a.get('tracknumber') or [None])[0]
        disc = (a.get('discnumber') or [None])[0]
    except Exception:
        pass
    return (title or os.path.splitext(os.path.basename(path))[0],
            _int(track), _int(disc), float(dur))


def index_library(con, music_path, progress=None):
    """Scan music_path into the db. progress(artists, albums, tracks) is called
    per album. Returns the final (artists, albums, tracks) counts."""
    lib = Library(music_path)
    n_art = n_alb = n_trk = 0
    for artist in lib.get_artists():
        con.execute("INSERT OR IGNORE INTO artists(name, sort_name) VALUES (?,?)",
                    (artist.name, artist.name.lower()))
        artist_id = con.execute("SELECT id FROM artists WHERE name=?",
                                (artist.name,)).fetchone()["id"]
        n_art += 1
        for al in artist.albums:
            con.execute("INSERT OR IGNORE INTO albums"
                        "(artist_id, name, year, folder, path, cover_path) "
                        "VALUES (?,?,?,?,?,?)",
                        (artist_id, al.display_name, al.year, al.folder_name,
                         al.path, al.cover_path))
            album_id = con.execute("SELECT id FROM albums WHERE path=?",
                                   (al.path,)).fetchone()["id"]
            con.execute("UPDATE albums SET name=?, year=?, cover_path=? WHERE id=?",
                        (al.display_name, al.year, al.cover_path, album_id))
            n_alb += 1
            for fn in lib.get_album_tracks(al.path):
                path = os.path.join(al.path, fn)
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                row = con.execute("SELECT mtime FROM tracks WHERE path=?",
                                  (path,)).fetchone()
                n_trk += 1
                if row and abs(row["mtime"] - mtime) < 1.0:
                    continue                      # unchanged — skip the tag read
                title, trk, disc, dur = read_tags(path)
                con.execute("INSERT OR IGNORE INTO tracks"
                            "(album_id, artist_id, title, track_no, disc_no, path, "
                            " duration, mtime) VALUES (?,?,?,?,?,?,?,?)",
                            (album_id, artist_id, title, trk, disc, path, dur, mtime))
                con.execute("UPDATE tracks SET title=?, track_no=?, disc_no=?, "
                            "duration=?, mtime=? WHERE path=?",
                            (title, trk, disc, dur, mtime, path))
            con.commit()
            if progress:
                progress(n_art, n_alb, n_trk)
    con.commit()
    return n_art, n_alb, n_trk
