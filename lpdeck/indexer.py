"""Index the music library into SQLite (track-level).

The library is a folder tree, Artist/Album/tracks, read with the same rules as
the kiosk's lpcore.library: album folder names and years, which files are tracks
and in what order (lpcore.tracks), and covers (lpcore.covers). Tags and length
come from mutagen. Designed to run on a background thread with its own
connection. One walk of the tree:

* Unchanged files keep their row and aren't re-read. In quick mode, an album
  folder whose modified time hasn't changed isn't even listed.
* A file that disappears is marked missing rather than deleted, so playlists,
  favourites, ratings and play history survive a share that's briefly away, a
  renamed album folder, or a move to a new library folder.
* A new file that is the same recording as one that vanished (same file name,
  same length) takes over its row, carrying that history with it; a renamed
  album's vinyl look moves with its tracks.
* Missing tracks nobody kept anything for (no playlist, favourite, rating or
  play) are deleted; albums and artists with nothing available are hidden.
"""
import os
from collections import Counter, defaultdict

from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3

from lpcore.covers import find_cover
from lpcore.library import parse_album_folder
from lpcore.tracks import is_audio, natural_key


def _int(v):
    try:
        return int(str(v).split('/')[0])
    except (TypeError, ValueError):
        return 0


def read_tags(path):
    """(title, track_no, disc_no, duration, genre) — title falls back to the
    filename. Handles mp3/flac directly and everything else mutagen can read
    (m4a, ogg/opus, wav, …) via the generic loader."""
    title = track = disc = genre = None
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
            mf = MutagenFile(path, easy=True)
            a = mf or {}
            if mf is not None and mf.info is not None:
                dur = float(getattr(mf.info, 'length', 0.0) or 0.0)
        title = (a.get('title') or [None])[0]
        track = (a.get('tracknumber') or [None])[0]
        disc = (a.get('discnumber') or [None])[0]
        genre = (a.get('genre') or [None])[0]
    except Exception:
        pass
    return (title or os.path.splitext(os.path.basename(path))[0],
            _int(track), _int(disc), float(dur), genre or '')


def _entries(path):
    """[(name, is_dir)] for a folder, or None when it can't be read."""
    try:
        return [(e.name, e.is_dir()) for e in os.scandir(path)]
    except OSError:
        return None


class _Relinker:
    """Finds the vanished track a newly seen file is the same recording as."""

    def __init__(self, con):
        self._by_name = defaultdict(list)
        for r in con.execute("SELECT id, path, duration, track_no, album_id, artist_id FROM tracks"):
            self._by_name[os.path.basename(r["path"])].append(dict(r))

    def take(self, path, duration, track_no):
        """A track row whose file is gone and that matches `path`: same file name,
        length within a second, and the same track number when both have one.
        One from an album folder of the same name is preferred."""
        name = os.path.basename(path)
        candidates = [r for r in self._by_name.get(name, ())
                      if r["path"] != path
                      and abs((r["duration"] or 0) - duration) < 1.0
                      and (not r["track_no"] or not track_no or r["track_no"] == track_no)
                      and not os.path.exists(r["path"])]
        if not candidates:
            return None
        folder = os.path.basename(os.path.dirname(path))
        candidates.sort(key=lambda r: os.path.basename(os.path.dirname(r["path"])) != folder)
        best = candidates[0]
        self._by_name[name].remove(best)
        return best


def index_library(con, music_path, progress=None, quick=False):
    """Scan music_path into the db. progress(artists, albums, tracks) is called
    per album. `quick` skips album folders whose modified time hasn't changed
    (a full scan still catches edits to files inside them, like retagging).
    Returns the (artists, albums, tracks) found.

    Raises OSError, changing nothing, when the folder can't be read or holds no
    music while the library had some: that's an unmounted share, not a library
    whose every track was deleted.
    """
    root = os.path.normpath(music_path)
    top = _entries(root)
    if top is None:
        raise OSError(f"music folder not reachable: {root}")

    known = {r["path"]: dict(r) for r in con.execute(
        "SELECT id, path, dir_mtime, missing FROM albums")}
    relinker = _Relinker(con)
    seen = set()                                  # ids of tracks present on disk
    moved_albums = defaultdict(Counter)           # old album id -> Counter(new album id)
    moved_artists = defaultdict(Counter)
    n_art = n_alb = n_trk = 0

    for artist_name, is_dir in sorted(top):
        if not is_dir:
            continue
        artist_path = os.path.join(root, artist_name)
        album_entries = _entries(artist_path)
        if album_entries is None:
            continue
        artist_id = None
        artist_counted = False

        for album_folder, is_album_dir in sorted(album_entries):
            if not is_album_dir:
                continue
            album_path = os.path.join(artist_path, album_folder)
            try:
                dir_mtime = os.stat(album_path).st_mtime
            except OSError:
                continue
            row = known.get(album_path)

            if quick and row and not row["missing"] and abs(row["dir_mtime"] - dir_mtime) < 1e-3:
                ids = [r["id"] for r in con.execute(
                    "SELECT id FROM tracks WHERE album_id=? AND missing=0", (row["id"],))]
                if ids:
                    seen.update(ids)
                    n_art += 0 if artist_counted else 1
                    artist_counted = True
                    n_alb += 1
                    n_trk += len(ids)
                    if progress:
                        progress(n_art, n_alb, n_trk)
                    continue

            listing = _entries(album_path)
            if listing is None:
                continue
            files = [n for n, d in listing if not d]
            track_names = sorted((n for n in files if is_audio(n)), key=natural_key)
            if not track_names:
                continue

            if artist_id is None:
                con.execute("INSERT OR IGNORE INTO artists(name, sort_name) VALUES (?,?)",
                            (artist_name, artist_name.lower()))
                artist_id = con.execute("SELECT id FROM artists WHERE name=?",
                                        (artist_name,)).fetchone()["id"]
            n_art += 0 if artist_counted else 1
            artist_counted = True

            year, display = parse_album_folder(album_folder)
            track_paths = [os.path.join(album_path, n) for n in track_names]
            cover = find_cover(album_path, track_paths[:2], names=files)
            con.execute("INSERT OR IGNORE INTO albums(artist_id, name, year, folder, path, cover_path) "
                        "VALUES (?,?,?,?,?,?)",
                        (artist_id, display, year, album_folder, album_path, cover))
            album_id = con.execute("SELECT id FROM albums WHERE path=?",
                                   (album_path,)).fetchone()["id"]
            con.execute("UPDATE albums SET artist_id=?, name=?, year=?, folder=?, cover_path=?, "
                        "missing=0 WHERE id=?",
                        (artist_id, display, year, album_folder, cover, album_id))
            n_alb += 1

            for path in track_paths:
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                n_trk += 1
                existing = con.execute("SELECT id, mtime, missing FROM tracks WHERE path=?",
                                       (path,)).fetchone()
                if existing and abs(existing["mtime"] - mtime) < 1.0:
                    if existing["missing"]:
                        con.execute("UPDATE tracks SET missing=0 WHERE id=?", (existing["id"],))
                    seen.add(existing["id"])
                    continue
                title, trk, disc, dur, genre = read_tags(path)
                if existing:
                    con.execute("UPDATE tracks SET album_id=?, artist_id=?, title=?, track_no=?, "
                                "disc_no=?, duration=?, mtime=?, genre=?, missing=0 WHERE id=?",
                                (album_id, artist_id, title, trk, disc, dur, mtime, genre,
                                 existing["id"]))
                    seen.add(existing["id"])
                    continue
                old = relinker.take(path, dur, trk)
                if old:
                    con.execute("UPDATE tracks SET path=?, album_id=?, artist_id=?, title=?, "
                                "track_no=?, disc_no=?, duration=?, mtime=?, genre=?, missing=0 "
                                "WHERE id=?",
                                (path, album_id, artist_id, title, trk, disc, dur, mtime, genre,
                                 old["id"]))
                    if old["album_id"] != album_id:
                        moved_albums[old["album_id"]][album_id] += 1
                    if old["artist_id"] != artist_id:
                        moved_artists[old["artist_id"]][artist_id] += 1
                    seen.add(old["id"])
                    continue
                cur = con.execute("INSERT INTO tracks(album_id, artist_id, title, track_no, disc_no, "
                                  "path, duration, mtime, genre, added_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (album_id, artist_id, title, trk, disc, path, dur, mtime, genre,
                                   mtime))
                seen.add(cur.lastrowid)

            # recorded last, so an album interrupted mid-scan is listed again next time
            con.execute("UPDATE albums SET dir_mtime=? WHERE id=?", (dir_mtime, album_id))
            con.commit()
            if progress:
                progress(n_art, n_alb, n_trk)

    available = con.execute("SELECT COUNT(*) FROM tracks WHERE missing=0").fetchone()[0]
    if n_trk == 0 and available:
        con.rollback()
        raise OSError(f"no music found in {root}; leaving the library as it was")

    _finish(con, seen, moved_albums, moved_artists)
    return n_art, n_alb, n_trk


def _finish(con, seen, moved_albums, moved_artists):
    """Mark what wasn't seen missing, carry vinyl looks over to renamed albums and
    artists, and tidy away rows nothing depends on."""
    con.execute("CREATE TEMP TABLE IF NOT EXISTS scan_seen(id INTEGER PRIMARY KEY)")
    con.execute("DELETE FROM scan_seen")
    con.executemany("INSERT INTO scan_seen(id) VALUES (?)", [(i,) for i in seen])
    con.execute("UPDATE tracks SET missing=1 WHERE missing=0 AND id NOT IN (SELECT id FROM scan_seen)")
    con.execute("UPDATE tracks SET missing=0 WHERE missing=1 AND id IN (SELECT id FROM scan_seen)")

    for scope, moved, table, column in (("album", moved_albums, "tracks", "album_id"),
                                        ("artist", moved_artists, "tracks", "artist_id")):
        for old_id, targets in moved.items():
            if con.execute(f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1", (old_id,)).fetchone():
                continue                          # only some tracks moved: the look stays
            new_id = targets.most_common(1)[0][0]
            if not con.execute("SELECT 1 FROM vinyl_overrides WHERE scope=? AND scope_id=?",
                               (scope, new_id)).fetchone():
                con.execute("UPDATE vinyl_overrides SET scope_id=? WHERE scope=? AND scope_id=?",
                            (new_id, scope, old_id))

    con.execute("DELETE FROM tracks WHERE missing=1 AND favorite=0 AND rating=0 AND play_count=0 "
                "AND id NOT IN (SELECT track_id FROM playlist_tracks) "
                "AND id NOT IN (SELECT track_id FROM play_history)")
    con.execute("DELETE FROM albums WHERE id NOT IN (SELECT DISTINCT album_id FROM tracks)")
    con.execute("UPDATE albums SET missing = NOT EXISTS "
                "(SELECT 1 FROM tracks t WHERE t.album_id=albums.id AND t.missing=0)")
    con.execute("DELETE FROM artists WHERE id NOT IN (SELECT DISTINCT artist_id FROM albums) "
                "AND id NOT IN (SELECT DISTINCT artist_id FROM tracks)")
    con.execute("UPDATE artists SET missing = NOT EXISTS "
                "(SELECT 1 FROM albums al WHERE al.artist_id=artists.id AND al.missing=0)")
    con.execute("DELETE FROM vinyl_overrides WHERE scope='album' AND scope_id NOT IN (SELECT id FROM albums)")
    con.execute("DELETE FROM vinyl_overrides WHERE scope='artist' AND scope_id NOT IN (SELECT id FROM artists)")
    con.commit()
