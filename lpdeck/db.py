"""SQLite storage for lp-deck (req #8).

Holds the library index (artists / albums / tracks — track-level, unlike the
kiosk's album-only model), playlists + ordering, and vinyl-setting overrides at
three scopes (global / artist / album, req #7). Pure stdlib; no Qt here so it's
testable on its own.

Resolution order for vinyl settings: album override → artist override → global.
"""
import json
import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    sort_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS albums (
    id         INTEGER PRIMARY KEY,
    artist_id  INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    year       TEXT NOT NULL DEFAULT '',
    folder     TEXT NOT NULL DEFAULT '',
    path       TEXT NOT NULL UNIQUE,
    cover_path TEXT
);

CREATE TABLE IF NOT EXISTS tracks (
    id         INTEGER PRIMARY KEY,
    album_id   INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    artist_id  INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    title      TEXT NOT NULL DEFAULT '',
    track_no   INTEGER NOT NULL DEFAULT 0,
    disc_no    INTEGER NOT NULL DEFAULT 0,
    path       TEXT NOT NULL UNIQUE,
    duration   REAL NOT NULL DEFAULT 0,
    mtime      REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS playlists (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id    INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, position)
);

-- Vinyl-setting overrides. scope ∈ ('global','artist','album'); scope_id is the
-- artists.id / albums.id (NULL for global). `settings` is a VinylSettings dict.
CREATE TABLE IF NOT EXISTS vinyl_overrides (
    scope    TEXT NOT NULL,
    scope_id INTEGER,
    settings TEXT NOT NULL,
    PRIMARY KEY (scope, scope_id)
);

-- Play history: one row per track play (for "recently played" + stats).
CREATE TABLE IF NOT EXISTS play_history (
    id        INTEGER PRIMARY KEY,
    track_id  INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    played_at REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_id);
CREATE INDEX IF NOT EXISTS idx_tracks_album  ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_id);
CREATE INDEX IF NOT EXISTS idx_history_track ON play_history(track_id);
CREATE INDEX IF NOT EXISTS idx_history_time  ON play_history(played_at);
"""

# Columns added after the initial schema shipped — applied idempotently to
# existing databases (CREATE TABLE IF NOT EXISTS won't add columns).
_MIGRATIONS = [
    ("tracks", "favorite",    "INTEGER NOT NULL DEFAULT 0"),
    ("tracks", "rating",      "INTEGER NOT NULL DEFAULT 0"),
    ("tracks", "play_count",  "INTEGER NOT NULL DEFAULT 0"),
    ("tracks", "last_played", "REAL NOT NULL DEFAULT 0"),
    ("tracks", "genre",       "TEXT NOT NULL DEFAULT ''"),
    ("tracks", "added_at",    "REAL NOT NULL DEFAULT 0"),
]


def _migrate(con):
    for table, col, decl in _MIGRATIONS:
        cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    con.commit()


def connect(db_path):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    _migrate(con)
    return con


# --- vinyl override resolution (req #7) ---

def get_vinyl_override(con, scope, scope_id=None):
    # Newest row wins. Databases written before the set_vinyl_override fix below
    # can hold several global rows; without the ORDER BY, SQLite hands back the
    # oldest and the setting looks frozen at its first-ever value.
    row = con.execute(
        "SELECT settings FROM vinyl_overrides WHERE scope=? AND scope_id IS ? "
        "ORDER BY rowid DESC LIMIT 1",
        (scope, scope_id)).fetchone()
    return json.loads(row["settings"]) if row else None


def set_vinyl_override(con, scope, scope_id, settings_dict):
    # Delete-then-insert rather than ON CONFLICT: the global scope stores
    # scope_id NULL, and SQLite counts NULLs as distinct in a UNIQUE/PK index, so
    # ON CONFLICT(scope, scope_id) never matched an existing global row. Every
    # save appended instead of replacing, and the global vinyl look was stuck on
    # whatever was chosen first. `IS` matches NULL, so one path covers both.
    # Both statements share the implicit transaction closed by commit().
    con.execute("DELETE FROM vinyl_overrides WHERE scope=? AND scope_id IS ?",
                (scope, scope_id))
    con.execute(
        "INSERT INTO vinyl_overrides(scope, scope_id, settings) VALUES (?,?,?)",
        (scope, scope_id, json.dumps(settings_dict)))
    con.commit()


def clear_vinyl_override(con, scope, scope_id):
    con.execute("DELETE FROM vinyl_overrides WHERE scope=? AND scope_id IS ?",
                (scope, scope_id))
    con.commit()


def resolve_vinyl_settings(con, album_id=None, artist_id=None, playlist_id=None):
    """Most-specific override wins: album → artist → playlist → global → {}."""
    if album_id is not None:
        ov = get_vinyl_override(con, 'album', album_id)
        if ov:
            return ov
    if artist_id is not None:
        ov = get_vinyl_override(con, 'artist', artist_id)
        if ov:
            return ov
    if playlist_id is not None:
        ov = get_vinyl_override(con, 'playlist', playlist_id)
        if ov:
            return ov
    return get_vinyl_override(con, 'global', None) or {}


# --- library reads ---

def artist_cover_paths(con, artist_id, limit=4):
    """Up to `limit` cover paths for one artist (oldest first) — the per-tile
    query used by the QML image provider."""
    return [r["cover_path"] for r in con.execute(
        "SELECT cover_path FROM albums WHERE artist_id=? "
        "AND cover_path IS NOT NULL AND cover_path <> '' "
        "ORDER BY year, name LIMIT ?", (artist_id, limit))]


def artist_covers(con, limit=4):
    """{artist_id: [cover_path, …]} — up to `limit` covers per artist, oldest
    first, for the artist-tile mosaics. Skips artists/albums with no art."""
    out = {}
    for r in con.execute(
            "SELECT artist_id, cover_path FROM albums "
            "WHERE cover_path IS NOT NULL AND cover_path <> '' "
            "ORDER BY artist_id, year, name"):
        lst = out.setdefault(r["artist_id"], [])
        if len(lst) < limit:
            lst.append(r["cover_path"])
    return out


# --- playlists (req #1 Playlists, #3 queue source) ---

def create_playlist(con, name):
    cur = con.execute("INSERT INTO playlists(name, created_at) VALUES (?,?)",
                      (name, time.time()))
    con.commit()
    return cur.lastrowid


def playlist_track_ids(con, playlist_id):
    return [r["track_id"] for r in con.execute(
        "SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position",
        (playlist_id,))]


def append_to_playlist(con, playlist_id, track_id):
    n = con.execute("SELECT COALESCE(MAX(position)+1, 0) AS n FROM playlist_tracks "
                    "WHERE playlist_id=?", (playlist_id,)).fetchone()["n"]
    con.execute("INSERT INTO playlist_tracks(playlist_id, track_id, position) VALUES (?,?,?)",
                (playlist_id, track_id, n))
    con.commit()


def rename_playlist(con, playlist_id, name):
    con.execute("UPDATE playlists SET name=? WHERE id=?", (name, playlist_id))
    con.commit()


def delete_playlist(con, playlist_id):
    con.execute("DELETE FROM playlists WHERE id=?", (playlist_id,))
    con.commit()


def remove_playlist_position(con, playlist_id, position):
    """Remove the track at `position`, then compact the remaining positions so
    they stay contiguous (the PK is (playlist_id, position))."""
    ids = playlist_track_ids(con, playlist_id)
    if not (0 <= position < len(ids)):
        return
    del ids[position]
    con.execute("DELETE FROM playlist_tracks WHERE playlist_id=?", (playlist_id,))
    for pos, tid in enumerate(ids):
        con.execute("INSERT INTO playlist_tracks(playlist_id, track_id, position) "
                    "VALUES (?,?,?)", (playlist_id, tid, pos))
    con.commit()


# --- favorites / ratings ---

def set_favorite(con, track_id, fav):
    con.execute("UPDATE tracks SET favorite=? WHERE id=?", (1 if fav else 0, track_id))
    con.commit()


def set_rating(con, track_id, rating):
    con.execute("UPDATE tracks SET rating=? WHERE id=?",
                (max(0, min(5, int(rating))), track_id))
    con.commit()


def track_id_for_path(con, path):
    row = con.execute("SELECT id FROM tracks WHERE path=?", (path,)).fetchone()
    return row["id"] if row else None


# --- play stats / history ---

def record_play(con, track_id, when):
    con.execute("UPDATE tracks SET play_count=play_count+1, last_played=? WHERE id=?",
                (when, track_id))
    con.execute("INSERT INTO play_history(track_id, played_at) VALUES (?,?)",
                (track_id, when))
    con.commit()


def _track_rows(con, where, params, order, limit):
    return [dict(r) for r in con.execute(
        "SELECT t.id, t.title, t.duration, t.path, t.favorite, t.rating, "
        "t.play_count, t.album_id, al.path AS album_path, al.name AS album_name, "
        "t.artist_id, ar.name AS artist "
        "FROM tracks t JOIN albums al ON al.id=t.album_id "
        "JOIN artists ar ON ar.id=t.artist_id "
        f"WHERE {where} ORDER BY {order} LIMIT ?", (*params, limit))]


def recently_played(con, limit=100):
    return _track_rows(con, "t.last_played > 0", (), "t.last_played DESC", limit)


def most_played(con, limit=100):
    return _track_rows(con, "t.play_count > 0", (), "t.play_count DESC, t.last_played DESC", limit)


def recently_added(con, limit=100):
    return _track_rows(con, "t.added_at > 0", (), "t.added_at DESC", limit)


def favorites(con, limit=1000):
    return _track_rows(con, "t.favorite = 1", (), "ar.sort_name, al.year, t.track_no", limit)


def genres(con):
    return [r["genre"] for r in con.execute(
        "SELECT DISTINCT genre FROM tracks WHERE genre <> '' ORDER BY genre")]


def genre_tracks(con, genre, limit=1000):
    return _track_rows(con, "t.genre = ?", (genre,),
                       "ar.sort_name, al.year, t.track_no", limit)
