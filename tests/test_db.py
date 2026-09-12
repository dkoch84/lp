"""Tests for lpdeck.db — the SQLite library store.

The point: db.py holds play history, favourites, ratings and playlists, so a
regression here loses user data rather than mangling a pixel. The highest-risk
path is `_migrate()`: CREATE TABLE IF NOT EXISTS silently will not add a column,
so every column added after the first release reaches existing databases only
through that function. Those tests build a database at the ORIGINAL schema and
assert the upgrade both adds the columns and keeps the rows.

Pure stdlib + sqlite3; no Qt, no audio, no library scan.

    .venv/bin/python -m pytest tests/test_db.py
"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpdeck import db


# --- helpers ---------------------------------------------------------------

def _seed(con, artist="Artist", album="Album", tracks=("One", "Two", "Three"),
          year="1999", cover="/art/cover.jpg"):
    """Insert one artist + one album + `tracks`. Returns (artist_id, album_id,
    [track_id, ...])."""
    aid = con.execute("INSERT INTO artists(name, sort_name) VALUES (?,?)",
                      (artist, artist.lower())).lastrowid
    alid = con.execute(
        "INSERT INTO albums(artist_id, name, year, folder, path, cover_path) "
        "VALUES (?,?,?,?,?,?)",
        (aid, album, year, album, f"/music/{artist}/{album}", cover)).lastrowid
    tids = []
    for n, title in enumerate(tracks, start=1):
        tids.append(con.execute(
            "INSERT INTO tracks(album_id, artist_id, title, track_no, path, duration) "
            "VALUES (?,?,?,?,?,?)",
            (alid, aid, title, n, f"/music/{artist}/{album}/{n}.mp3", 100.0 + n)
        ).lastrowid)
    con.commit()
    return aid, alid, tids


@pytest.fixture
def con(tmp_path):
    c = db.connect(str(tmp_path / "lp-deck.db"))
    yield c
    c.close()


# --- migration (the high-risk path) ----------------------------------------

def _legacy_db(path):
    """A database at the ORIGINAL schema: SCHEMA only, no _migrate()."""
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript(db.SCHEMA)
    c.commit()
    return c


def test_legacy_db_really_lacks_the_migrated_columns(tmp_path):
    """Guard the premise of the tests below: if SCHEMA ever grows these columns
    directly, the migration tests would silently stop testing anything."""
    p = str(tmp_path / "legacy.db")
    c = _legacy_db(p)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(tracks)")}
    c.close()
    for _table, col, _decl in db._MIGRATIONS:
        assert col not in cols, f"SCHEMA already defines {col}; migration test is moot"


def test_migrate_adds_every_missing_column(tmp_path):
    p = str(tmp_path / "legacy.db")
    _legacy_db(p).close()

    con = db.connect(p)
    cols = {r["name"] for r in con.execute("PRAGMA table_info(tracks)")}
    con.close()

    for table, col, _decl in db._MIGRATIONS:
        assert table == "tracks"
        assert col in cols, f"_migrate did not add {col}"


def test_migrate_preserves_existing_rows_and_applies_defaults(tmp_path):
    """An upgrade must not drop the user's library, and pre-existing rows must
    come out with the column defaults rather than NULL."""
    p = str(tmp_path / "legacy.db")
    old = _legacy_db(p)
    _seed(old, tracks=("Kept",))
    old.close()

    con = db.connect(p)
    row = con.execute("SELECT * FROM tracks").fetchone()
    con.close()

    assert row["title"] == "Kept"
    assert row["favorite"] == 0
    assert row["rating"] == 0
    assert row["play_count"] == 0
    assert row["last_played"] == 0
    assert row["genre"] == ""
    assert row["added_at"] == 0


def test_migrate_is_idempotent(tmp_path):
    """connect() runs _migrate() every time, so opening an already-migrated
    database must not raise "duplicate column name"."""
    p = str(tmp_path / "lp.db")
    for _ in range(3):
        c = db.connect(p)
        c.close()

    c = db.connect(p)
    cols = [r["name"] for r in c.execute("PRAGMA table_info(tracks)")]
    c.close()
    assert len(cols) == len(set(cols)), "a column was added twice"


# --- vinyl override resolution (album > artist > playlist > global) ---------

def test_resolve_returns_empty_dict_when_nothing_is_set(con):
    assert db.resolve_vinyl_settings(con, album_id=1, artist_id=1) == {}


def test_resolve_prefers_album_over_artist_over_global(con):
    aid, alid, _ = _seed(con)
    db.set_vinyl_override(con, "global", None, {"style": "black"})
    assert db.resolve_vinyl_settings(con, album_id=alid, artist_id=aid)["style"] == "black"

    db.set_vinyl_override(con, "artist", aid, {"style": "color-teal"})
    assert db.resolve_vinyl_settings(con, album_id=alid, artist_id=aid)["style"] == "color-teal"

    db.set_vinyl_override(con, "album", alid, {"style": "color-gold"})
    assert db.resolve_vinyl_settings(con, album_id=alid, artist_id=aid)["style"] == "color-gold"


def test_resolve_falls_through_to_global_for_an_unset_album(con):
    aid, _alid, _ = _seed(con)
    db.set_vinyl_override(con, "global", None, {"style": "black"})
    db.set_vinyl_override(con, "album", 999, {"style": "color-gold"})
    got = db.resolve_vinyl_settings(con, album_id=12345, artist_id=aid)
    assert got == {"style": "black"}


@pytest.mark.parametrize("scope,scope_id", [("global", None), ("album", 7)])
def test_set_vinyl_override_replaces_rather_than_duplicating(con, scope, scope_id):
    """Regression: the global scope stores scope_id NULL, and SQLite counts
    NULLs as distinct in a UNIQUE index, so the old ON CONFLICT never fired.
    Each save appended a row and the reader returned the OLDEST, which froze the
    global vinyl look at whatever was picked first."""
    db.set_vinyl_override(con, scope, scope_id, {"style": "black"})
    db.set_vinyl_override(con, scope, scope_id, {"style": "color-gold"})
    db.set_vinyl_override(con, scope, scope_id, {"style": "clear"})

    n = con.execute("SELECT COUNT(*) AS n FROM vinyl_overrides").fetchone()["n"]
    assert n == 1, "override rows accumulated instead of being replaced"
    assert db.get_vinyl_override(con, scope, scope_id) == {"style": "clear"}


def test_global_override_reads_newest_from_an_already_duplicated_db(con):
    """Databases written before the fix already hold several global rows. The
    reader must serve the newest so those installs come good without a repair
    step."""
    for style in ("black", "color-gold", "clear"):
        con.execute("INSERT INTO vinyl_overrides(scope, scope_id, settings) "
                    "VALUES ('global', NULL, ?)", (f'{{"style": "{style}"}}',))
    con.commit()
    assert db.get_vinyl_override(con, "global", None) == {"style": "clear"}
    assert db.resolve_vinyl_settings(con) == {"style": "clear"}


def test_setting_a_global_override_collapses_pre_existing_duplicates(con):
    for style in ("black", "color-gold"):
        con.execute("INSERT INTO vinyl_overrides(scope, scope_id, settings) "
                    "VALUES ('global', NULL, ?)", (f'{{"style": "{style}"}}',))
    con.commit()

    db.set_vinyl_override(con, "global", None, {"style": "clear"})
    n = con.execute("SELECT COUNT(*) AS n FROM vinyl_overrides").fetchone()["n"]
    assert n == 1


def test_clear_vinyl_override(con):
    db.set_vinyl_override(con, "global", None, {"style": "black"})
    db.clear_vinyl_override(con, "global", None)
    assert db.get_vinyl_override(con, "global", None) is None


def test_override_settings_survive_a_round_trip_as_json(con):
    settings = {"style": "mandelbrot-seahorse", "label": "white",
                "brightness": 0.75, "decor": True, "text": None}
    db.set_vinyl_override(con, "global", None, settings)
    assert db.get_vinyl_override(con, "global", None) == settings


# --- playlists -------------------------------------------------------------

def test_playlist_append_keeps_insertion_order(con):
    _a, _al, tids = _seed(con)
    pid = db.create_playlist(con, "Mix")
    for t in reversed(tids):
        db.append_to_playlist(con, pid, t)
    assert db.playlist_track_ids(con, pid) == list(reversed(tids))


def test_remove_playlist_position_compacts_positions(con):
    """positions are the PK, so a gap left behind would collide on the next
    append. Removing the middle track must renumber the rest."""
    _a, _al, tids = _seed(con)
    pid = db.create_playlist(con, "Mix")
    for t in tids:
        db.append_to_playlist(con, pid, t)

    db.remove_playlist_position(con, pid, 1)
    assert db.playlist_track_ids(con, pid) == [tids[0], tids[2]]

    positions = [r["position"] for r in con.execute(
        "SELECT position FROM playlist_tracks WHERE playlist_id=? ORDER BY position",
        (pid,))]
    assert positions == [0, 1], "positions left non-contiguous"

    db.append_to_playlist(con, pid, tids[1])
    assert db.playlist_track_ids(con, pid) == [tids[0], tids[2], tids[1]]


def test_remove_playlist_position_ignores_out_of_range(con):
    _a, _al, tids = _seed(con)
    pid = db.create_playlist(con, "Mix")
    db.append_to_playlist(con, pid, tids[0])
    db.remove_playlist_position(con, pid, 7)
    db.remove_playlist_position(con, pid, -1)
    assert db.playlist_track_ids(con, pid) == [tids[0]]


def test_rename_playlist(con):
    pid = db.create_playlist(con, "Old")
    db.rename_playlist(con, pid, "New")
    assert con.execute("SELECT name FROM playlists WHERE id=?",
                       (pid,)).fetchone()["name"] == "New"


def test_delete_playlist_cascades_to_its_tracks(con):
    """playlist_tracks has ON DELETE CASCADE, which only fires because connect()
    turns foreign_keys ON per connection."""
    _a, _al, tids = _seed(con)
    pid = db.create_playlist(con, "Mix")
    for t in tids:
        db.append_to_playlist(con, pid, t)

    db.delete_playlist(con, pid)
    left = con.execute("SELECT COUNT(*) AS n FROM playlist_tracks "
                       "WHERE playlist_id=?", (pid,)).fetchone()["n"]
    assert left == 0, "orphaned playlist_tracks rows (foreign_keys off?)"


def test_deleting_a_track_cascades_out_of_playlists(con):
    _a, _al, tids = _seed(con)
    pid = db.create_playlist(con, "Mix")
    for t in tids:
        db.append_to_playlist(con, pid, t)

    con.execute("DELETE FROM tracks WHERE id=?", (tids[0],))
    con.commit()
    assert db.playlist_track_ids(con, pid) == tids[1:]


# --- favourites / ratings --------------------------------------------------

def test_set_favorite_round_trip(con):
    _a, _al, tids = _seed(con)
    db.set_favorite(con, tids[0], True)
    assert [r["id"] for r in db.favorites(con)] == [tids[0]]
    db.set_favorite(con, tids[0], False)
    assert db.favorites(con) == []


@pytest.mark.parametrize("given,expected", [
    (-3, 0), (0, 0), (3, 3), (5, 5), (99, 5),
])
def test_set_rating_clamps_to_zero_through_five(con, given, expected):
    _a, _al, tids = _seed(con)
    db.set_rating(con, tids[0], given)
    got = con.execute("SELECT rating FROM tracks WHERE id=?",
                      (tids[0],)).fetchone()["rating"]
    assert got == expected


def test_track_id_for_path(con):
    _a, _al, tids = _seed(con)
    path = con.execute("SELECT path FROM tracks WHERE id=?",
                       (tids[1],)).fetchone()["path"]
    assert db.track_id_for_path(con, path) == tids[1]
    assert db.track_id_for_path(con, "/nope.mp3") is None


# --- play history / smart lists --------------------------------------------

def test_record_play_bumps_count_and_writes_history(con):
    _a, _al, tids = _seed(con)
    db.record_play(con, tids[0], 1000.0)
    db.record_play(con, tids[0], 2000.0)

    row = con.execute("SELECT play_count, last_played FROM tracks WHERE id=?",
                      (tids[0],)).fetchone()
    assert row["play_count"] == 2
    assert row["last_played"] == 2000.0

    hist = [r["played_at"] for r in con.execute(
        "SELECT played_at FROM play_history WHERE track_id=? ORDER BY played_at",
        (tids[0],))]
    assert hist == [1000.0, 2000.0]


def test_recently_played_is_most_recent_first_and_excludes_unplayed(con):
    _a, _al, tids = _seed(con)
    db.record_play(con, tids[0], 1000.0)
    db.record_play(con, tids[2], 3000.0)
    assert [r["id"] for r in db.recently_played(con)] == [tids[2], tids[0]]


def test_most_played_orders_by_count(con):
    _a, _al, tids = _seed(con)
    for _ in range(3):
        db.record_play(con, tids[1], 10.0)
    db.record_play(con, tids[0], 20.0)
    assert [r["id"] for r in db.most_played(con)] == [tids[1], tids[0]]


def test_smart_lists_respect_their_limit(con):
    _a, _al, tids = _seed(con)
    for i, t in enumerate(tids):
        db.record_play(con, t, 100.0 + i)
    assert len(db.recently_played(con, limit=2)) == 2


def test_recently_added_needs_added_at(con):
    _a, _al, tids = _seed(con)
    assert db.recently_added(con) == []
    con.execute("UPDATE tracks SET added_at=? WHERE id=?", (500.0, tids[0]))
    con.commit()
    assert [r["id"] for r in db.recently_added(con)] == [tids[0]]


def test_track_rows_carry_the_album_and_artist_join(con):
    _a, _al, tids = _seed(con, artist="Bowie", album="Low")
    db.record_play(con, tids[0], 1.0)
    row = db.recently_played(con)[0]
    assert row["artist"] == "Bowie"
    assert row["album_name"] == "Low"
    assert row["album_path"].endswith("/Bowie/Low")


# --- genres ----------------------------------------------------------------

def test_genres_are_distinct_sorted_and_skip_blanks(con):
    _a, _al, tids = _seed(con)
    con.execute("UPDATE tracks SET genre='Rock' WHERE id=?", (tids[0],))
    con.execute("UPDATE tracks SET genre='Ambient' WHERE id=?", (tids[1],))
    con.execute("UPDATE tracks SET genre='Rock' WHERE id=?", (tids[2],))
    con.commit()
    assert db.genres(con) == ["Ambient", "Rock"]


def test_genre_tracks_filters(con):
    _a, _al, tids = _seed(con)
    con.execute("UPDATE tracks SET genre='Rock' WHERE id=?", (tids[0],))
    con.commit()
    assert [r["id"] for r in db.genre_tracks(con, "Rock")] == [tids[0]]
    assert db.genre_tracks(con, "Jazz") == []


# --- library reads ---------------------------------------------------------

def test_artist_cover_paths_skips_albums_without_art(con):
    aid, _al, _ = _seed(con, cover="/art/a.jpg")
    con.execute("INSERT INTO albums(artist_id, name, year, folder, path, cover_path) "
                "VALUES (?,?,?,?,?,?)", (aid, "B", "2001", "B", "/music/B", ""))
    con.execute("INSERT INTO albums(artist_id, name, year, folder, path, cover_path) "
                "VALUES (?,?,?,?,?,?)", (aid, "C", "2002", "C", "/music/C", None))
    con.commit()
    assert db.artist_cover_paths(con, aid) == ["/art/a.jpg"]


def test_artist_covers_caps_per_artist(con):
    aid, _al, _ = _seed(con, cover="/art/1.jpg")
    for i in range(2, 8):
        con.execute("INSERT INTO albums(artist_id, name, year, folder, path, cover_path) "
                    "VALUES (?,?,?,?,?,?)",
                    (aid, f"A{i}", f"20{i:02d}", f"A{i}", f"/music/A{i}", f"/art/{i}.jpg"))
    con.commit()
    assert len(db.artist_covers(con, limit=4)[aid]) == 4
