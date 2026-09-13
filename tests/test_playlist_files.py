"""Tests for reading and writing playlist files (M3U / M3U8, PLS, XSPF).

Playlists come from other players and other computers: relative entries, file://
URLs with escapes, Windows separators, Latin-1 text and web streams all turn up.

    .venv/bin/python -m pytest tests/test_playlist_files.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpdeck.playlist_files import format_for, read_playlist, write_playlist

TRACKS = [
    {'path': '/music/Pallbearer/Heartless/01 I Saw the End.flac', 'title': 'I Saw the End',
     'artist': 'Pallbearer', 'duration': 519.0},
    {'path': '/music/Sleep/Dopesmoker/01 Dopesmoker #1 (100%).flac', 'title': 'Dopesmoker',
     'artist': 'Sleep', 'duration': 3780.0},
    {'path': '/music/Björk/Homogenic/02 Hunter.flac'},
]


def test_format_from_extension():
    assert format_for('a.M3U8') == 'm3u'
    assert format_for('a.m3u') == 'm3u'
    assert format_for('a.pls') == 'pls'
    assert format_for('a.xspf') == 'xspf'
    assert format_for('a.txt') is None


@pytest.mark.parametrize('name', ['list.m3u8', 'list.m3u', 'list.pls', 'list.xspf'])
def test_round_trip(tmp_path, name):
    path = str(tmp_path / name)
    write_playlist(path, TRACKS)
    back = read_playlist(path)
    assert [t['path'] for t in back] == [t['path'] for t in TRACKS]
    assert back[0]['title'] == 'I Saw the End'
    assert back[1]['duration'] == pytest.approx(3780.0)
    assert 'duration' not in back[2]           # unknown length stays unknown
    assert not os.path.exists(path + '.tmp')


def test_m3u_extinf_relative_paths_comments_and_streams(tmp_path):
    (tmp_path / 'list.m3u').write_text(
        '#EXTM3U\n'
        '#EXTINF:519,Pallbearer - I Saw the End\n'
        'Pallbearer/Heartless/01.flac\n'
        '\n'
        '# a comment\n'
        'http://radio.example/stream\n'
        '/abs/02.flac\n'
        '#EXTINF:-1,Untitled\n'
        'file:///abs/with%20space.flac\n')
    entries = read_playlist(str(tmp_path / 'list.m3u'))
    assert entries == [
        {'path': str(tmp_path / 'Pallbearer/Heartless/01.flac'), 'duration': 519.0,
         'artist': 'Pallbearer', 'title': 'I Saw the End'},
        {'path': '/abs/02.flac'},
        {'path': '/abs/with space.flac', 'title': 'Untitled'},
    ]


def test_windows_separators_and_latin1(tmp_path):
    (tmp_path / 'list.m3u').write_bytes('Bj\xf6rk\\Homogenic\\02 Hunter.flac\r\n'.encode('latin-1'))
    [entry] = read_playlist(str(tmp_path / 'list.m3u'))
    assert entry['path'] == str(tmp_path / 'Björk' / 'Homogenic' / '02 Hunter.flac')


def test_pls_numbering_out_of_order(tmp_path):
    (tmp_path / 'list.pls').write_text(
        '[playlist]\n'
        'File2=/b.flac\nTitle2=Second\nLength2=-1\n'
        'File1=/a.flac\nLength1=60\n'
        'NumberOfEntries=2\nVersion=2\n')
    assert read_playlist(str(tmp_path / 'list.pls')) == [
        {'path': '/a.flac', 'duration': 60.0},
        {'path': '/b.flac', 'title': 'Second'},
    ]


def test_xspf_without_a_namespace(tmp_path):
    (tmp_path / 'list.xspf').write_text(
        '<playlist version="1"><trackList>'
        '<track><location>file:///a%23b.flac</location><creator>X</creator>'
        '<duration>1500</duration></track>'
        '<track><location>https://example.com/x.mp3</location></track>'
        '</trackList></playlist>')
    assert read_playlist(str(tmp_path / 'list.xspf')) == [
        {'path': '/a#b.flac', 'artist': 'X', 'duration': 1.5}]


def test_unknown_type_is_refused(tmp_path):
    with pytest.raises(ValueError):
        read_playlist(str(tmp_path / 'list.txt'))
    with pytest.raises(ValueError):
        write_playlist(str(tmp_path / 'list.txt'), TRACKS)
