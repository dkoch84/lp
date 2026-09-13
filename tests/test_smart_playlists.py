"""Tests for smart playlists you define (rules turned into a library query).

Rules are stored and replayed, so anything odd in a stored definition must be
ignored rather than reach the SQL.

    .venv/bin/python -m pytest tests/test_smart_playlists.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpdeck import db, smart

NOW = 1_800_000_000.0
DAY = 86400


def make_library(tmp_path):
    """A small library: two Pallbearer albums and Sleep's Dopesmoker (no year)."""
    con = db.connect(str(tmp_path / 'library.db'))

    def artist(name):
        return con.execute("INSERT INTO artists(name, sort_name) VALUES (?, ?)",
                           (name, name.lower())).lastrowid

    def album(artist_id, name, year):
        return con.execute("INSERT INTO albums(artist_id, name, year, path) VALUES (?,?,?,?)",
                           (artist_id, name, year, f"/music/{artist_id}/{name}")).lastrowid

    def track(album_id, artist_id, title, n, **cols):
        values = dict(album_id=album_id, artist_id=artist_id, title=title, track_no=n,
                      path=f"/music/{album_id}/{n}.flac", duration=200.0)
        values.update(cols)
        con.execute(f"INSERT INTO tracks({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
                    tuple(values.values()))

    pb, sl = artist('Pallbearer'), artist('Sleep')
    fob, heartless, dope = (album(pb, 'Foundations of Burden', '2014'),
                            album(pb, 'Heartless', '2017'), album(sl, 'Dopesmoker', ''))
    track(fob, pb, 'Worlds Apart', 1, genre='Doom Metal', play_count=12, favorite=1, rating=5,
          added_at=NOW - 100 * DAY, last_played=NOW - 2 * DAY)
    track(fob, pb, 'The Ghost I Used to Be', 2, genre='Doom Metal', play_count=3, duration=600.0,
          added_at=NOW - 100 * DAY, last_played=NOW - 40 * DAY)
    track(heartless, pb, 'I Saw the End', 1, genre='Doom Metal', added_at=NOW - 3 * DAY)
    track(dope, sl, 'Dopesmoker', 1, genre='Stoner 100%', play_count=7, duration=3800.0,
          added_at=NOW - 400 * DAY, last_played=NOW - DAY)
    con.commit()
    return con


def titles(con, definition):
    where, params, order, limit = smart.build_query(definition, now=NOW)
    return [r['title'] for r in db._track_rows(con, where, params, order, limit)]


def rule(field, op, value=None):
    return {'field': field, 'op': op, 'value': value}


def test_all_rules_must_match(tmp_path):
    con = make_library(tmp_path)
    assert titles(con, {'match': 'all', 'rules': [rule('artist', 'contains', 'pall'),
                                                  rule('plays', '>', 1)]}) == \
        ['Worlds Apart', 'The Ghost I Used to Be']


def test_any_rule_may_match(tmp_path):
    con = make_library(tmp_path)
    assert titles(con, {'match': 'any', 'rules': [rule('genre', 'is', 'STONER 100%'),
                                                  rule('favorite', 'is_true')]}) == \
        ['Worlds Apart', 'Dopesmoker']


def test_like_wildcards_in_values_are_literal(tmp_path):
    con = make_library(tmp_path)
    assert titles(con, {'rules': [rule('genre', 'contains', '%')]}) == ['Dopesmoker']
    assert titles(con, {'rules': [rule('title', 'contains', '_')]}) == []
    assert titles(con, {'rules': [rule('title', 'starts_with', 'the ')]}) == ['The Ghost I Used to Be']


def test_years_leave_out_albums_without_one(tmp_path):
    con = make_library(tmp_path)
    assert titles(con, {'rules': [rule('year', '>=', '2015')]}) == ['I Saw the End']
    assert titles(con, {'rules': [rule('year', '<', 2015)]}) == \
        ['Worlds Apart', 'The Ghost I Used to Be']


def test_dates(tmp_path):
    con = make_library(tmp_path)
    assert titles(con, {'rules': [rule('last_played', 'in_last_days', 7)]}) == \
        ['Worlds Apart', 'Dopesmoker']
    assert titles(con, {'rules': [rule('last_played', 'never')]}) == ['I Saw the End']
    assert titles(con, {'rules': [rule('last_played', 'not_in_last_days', '30')]}) == \
        ['The Ghost I Used to Be', 'I Saw the End']
    assert titles(con, {'rules': [rule('added', 'in_last_days', 7)]}) == ['I Saw the End']


def test_length_and_case_insensitive_is(tmp_path):
    con = make_library(tmp_path)
    assert titles(con, {'rules': [rule('length', '>', 1000)]}) == ['Dopesmoker']
    assert titles(con, {'rules': [rule('artist', 'is', 'sleep')]}) == ['Dopesmoker']
    assert titles(con, {'rules': [rule('artist', 'is_not', 'sleep')]}) == \
        ['Worlds Apart', 'The Ghost I Used to Be', 'I Saw the End']


def test_sort_and_limit(tmp_path):
    con = make_library(tmp_path)
    assert titles(con, {'rules': [], 'sort': 'plays', 'limit': 2}) == ['Worlds Apart', 'Dopesmoker']


def test_nonsense_in_a_stored_definition_is_ignored(tmp_path):
    con = make_library(tmp_path)
    got = titles(con, {'match': 'all', 'sort': 'title; DROP TABLE tracks', 'limit': 'lots', 'rules': [
        rule('path; DROP TABLE tracks', 'contains', 'x'),
        rule('year', '>', 'not a number'),
        rule('artist', '>', 'x'),                 # a number operator on a text field
        rule('favorite', 'contains', 'x'),
        'not even a rule',
    ]})
    assert len(got) == 4
    assert con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 4


def test_normalize_keeps_only_what_works():
    good = rule('genre', 'contains', 'doom')
    assert smart.normalize({'match': 'weird', 'rules': [good, rule('nope', 'is', 'x')],
                            'sort': 'nope', 'limit': 999999, 'extra': 1}) == \
        {'match': 'all', 'rules': [good], 'sort': 'artist', 'limit': 10000}


def test_stored_smart_playlists_follow_the_library(tmp_path):
    con = make_library(tmp_path)
    sid = db.create_smart_playlist(con, 'Doom', {'rules': [rule('genre', 'contains', 'doom')]})
    assert [t['title'] for t in db.smart_playlist_tracks(con, sid, now=NOW)] == \
        ['Worlds Apart', 'The Ghost I Used to Be', 'I Saw the End']

    con.execute("UPDATE tracks SET missing=1 WHERE title='Worlds Apart'")
    assert len(db.smart_playlist_tracks(con, sid, now=NOW)) == 2

    db.update_smart_playlist(con, sid, 'Old doom', {'rules': [rule('genre', 'contains', 'doom'),
                                                              rule('year', '<', 2015)]})
    [stored] = db.smart_playlists(con)
    assert stored['name'] == 'Old doom' and len(stored['definition']['rules']) == 2
    assert [t['title'] for t in db.smart_playlist_tracks(con, sid, now=NOW)] == \
        ['The Ghost I Used to Be']

    db.delete_smart_playlist(con, sid)
    assert db.smart_playlists(con) == []
    assert db.smart_playlist_tracks(con, sid) == []
