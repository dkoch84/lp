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

CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_id);
CREATE INDEX IF NOT EXISTS idx_tracks_album  ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_id);
"""


def connect(db_path):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


# --- vinyl override resolution (req #7) ---

def get_vinyl_override(con, scope, scope_id=None):
    row = con.execute(
        "SELECT settings FROM vinyl_overrides WHERE scope=? AND scope_id IS ?",
        (scope, scope_id)).fetchone()
    return json.loads(row["settings"]) if row else None


def set_vinyl_override(con, scope, scope_id, settings_dict):
    con.execute(
        "INSERT INTO vinyl_overrides(scope, scope_id, settings) VALUES (?,?,?) "
        "ON CONFLICT(scope, scope_id) DO UPDATE SET settings=excluded.settings",
        (scope, scope_id, json.dumps(settings_dict)))
    con.commit()


def clear_vinyl_override(con, scope, scope_id):
    con.execute("DELETE FROM vinyl_overrides WHERE scope=? AND scope_id IS ?",
                (scope, scope_id))
    con.commit()


def resolve_vinyl_settings(con, album_id=None, artist_id=None):
    """Most-specific override wins: album → artist → global → {} (renderer default)."""
    if album_id is not None:
        ov = get_vinyl_override(con, 'album', album_id)
        if ov:
            return ov
    if artist_id is not None:
        ov = get_vinyl_override(con, 'artist', artist_id)
        if ov:
            return ov
    return get_vinyl_override(con, 'global', None) or {}


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
