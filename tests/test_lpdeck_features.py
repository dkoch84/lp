"""Tests for lp-deck's library and desktop features in the controller: search by
field, all albums and all tracks, playlist import and export, smart playlists,
opening files from outside, fade on pause, the audio device, keeping the computer
awake and track-change notifications.

    .venv/bin/python -m pytest tests/test_lpdeck_features.py
"""
import os
import sys

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

pytest.importorskip('PySide6', reason='lp-deck needs PySide6 (requirements-deck.txt)')

from lpdeck import db
from lpdeck.playlist_files import read_playlist
from test_smart_playlists import make_library, rule


def _settings(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QGuiApplication
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / 'settings'))
    app = QGuiApplication.instance() or QGuiApplication([])
    app.setOrganizationName('lp-deck-test')
    app.setApplicationName('lp-deck-test')


def _controller(con):
    from lpdeck import qmlapp
    from lpdeck.shot import _FakeBackend, _FakePlayer
    player = _FakePlayer(_FakeBackend(con))
    return qmlapp.Controller(con, player, qmlapp.ArtistsModel(con), qmlapp.QueueModel(player))


@pytest.fixture
def con(tmp_path):
    _settings(tmp_path)
    return make_library(tmp_path)


@pytest.fixture
def c(con):
    return _controller(con)


def _names(items, key='name'):
    return [i[key] for i in items]


# --- search ---------------------------------------------------------------------------------

def test_plain_words_match_artists_albums_and_songs(c):
    r = c.search('pallbearer')
    assert _names(r['artists']) == ['Pallbearer']
    assert _names(r['albums']) == ['Foundations of Burden', 'Heartless']
    assert _names(r['songs'], 'title') == ['I Saw the End', 'The Ghost I Used to Be', 'Worlds Apart']


def test_field_filters_narrow_each_kind(c):
    r = c.search('artist:pallbearer year:>2015')
    assert r['artists'] == []                      # artists have no year
    assert _names(r['albums']) == ['Heartless']
    assert _names(r['songs'], 'title') == ['I Saw the End']

    r = c.search('title:dopesmoker')
    assert r['artists'] == [] and r['albums'] == []
    assert _names(r['songs'], 'title') == ['Dopesmoker']

    assert _names(c.search('genre:doom ghost')['songs'], 'title') == ['The Ghost I Used to Be']
    assert c.search('   ') == {'artists': [], 'albums': [], 'songs': []}


def test_a_found_song_knows_its_place_in_the_album(c):
    [song] = c.search('title:"the ghost"')['songs']
    assert song['index'] == 1 and song['album'] == 'Foundations of Burden'


def test_all_albums_and_all_tracks(c):
    albums = c.allAlbums()
    assert _names(albums) == ['Dopesmoker', 'Foundations of Burden', 'Heartless']
    assert albums[0]['artist'] == 'Sleep'
    c.setAlbumSort('name')
    assert _names(c.allAlbums()) == ['Dopesmoker', 'Foundations of Burden', 'Heartless']
    assert len(c.smartList('all')) == 4


# --- playlist files -------------------------------------------------------------------------

def test_import_matches_library_tracks_even_from_another_computer(c, tmp_path):
    playlist = tmp_path / 'Doom picks.m3u'
    playlist.write_text('#EXTM3U\n/music/1/2.flac\n/mnt/old-nas/music/1/1.flac\n/nowhere/x.flac\n')
    pid = c.importPlaylist(str(playlist))
    assert pid > 0
    assert _names(c.playlists()) == ['Doom picks']
    assert _names(c.playlistSongs(pid), 'title') == ['The Ghost I Used to Be', 'Worlds Apart']
    assert '2 songs' in c.notice and '1 not in your library' in c.notice


def test_import_failures_say_why(c, tmp_path):
    (tmp_path / 'strangers.m3u').write_text('/nowhere/a.flac\n')
    assert c.importPlaylist('file://' + str(tmp_path / 'strangers.m3u')) == -1
    assert 'None of the songs' in c.notice
    (tmp_path / 'broken.xspf').write_text('<playlist><trackList>')
    assert c.importPlaylist(str(tmp_path / 'broken.xspf')) == -1
    assert c.notice.startswith("Couldn't import broken.xspf")
    assert c.playlists() == []


def test_export_adds_an_extension_and_accepts_file_urls(c, con, tmp_path):
    pid = db.create_playlist(con, 'Doom')
    db.append_many_to_playlist(con, pid, [1, 3])
    assert c.exportPlaylist(pid, str(tmp_path / 'doom'))
    assert [e['path'] for e in read_playlist(str(tmp_path / 'doom.m3u8'))] == \
        ['/music/1/1.flac', '/music/2/1.flac']
    assert c.exportPlaylist(pid, 'file://' + str(tmp_path / 'doom.xspf'))
    assert read_playlist(str(tmp_path / 'doom.xspf'))[0]['title'] == 'Worlds Apart'
    assert not c.exportPlaylist(pid, str(tmp_path / 'no-such-dir' / 'doom.m3u'))
    assert c.notice.startswith("Couldn't save")


def test_export_the_queue_and_a_smart_playlist(c, tmp_path):
    c.player.set_queue([{'path': '/music/3/1.flac', 'title': 'Dopesmoker', 'artist': 'Sleep',
                         'duration': 3800.0}])
    assert c.exportQueue(str(tmp_path / 'queue.pls'))
    assert read_playlist(str(tmp_path / 'queue.pls'))[0]['path'] == '/music/3/1.flac'
    sid = c.saveSmartPlaylist(-1, 'Sleep', {'rules': [rule('artist', 'is', 'sleep')]})
    assert c.exportSmartPlaylist(sid, str(tmp_path / 'sleep.m3u'))
    assert len(read_playlist(str(tmp_path / 'sleep.m3u'))) == 1


# --- smart playlists ------------------------------------------------------------------------

def test_smart_playlists_through_the_controller(c):
    changed = []
    c.playlistsChanged.connect(lambda: changed.append(1))
    doom = {'match': 'all', 'rules': [rule('genre', 'contains', 'doom')], 'sort': 'artist'}
    sid = c.saveSmartPlaylist(-1, '  ', doom)
    assert c.smartPlaylists() == [{'id': sid, 'name': 'Smart playlist'}]
    assert len(c.smartPlaylistSongs(sid)) == 3
    assert c.saveSmartPlaylist(sid, 'Doom', {**doom, 'rules': doom['rules'] + [rule('plays', '>', 5)]}) == sid
    assert c.smartPlaylistDefinition(sid)['name'] == 'Doom'
    assert _names(c.smartPlaylistSongs(sid), 'title') == ['Worlds Apart']
    assert c.smartPreviewCount({'rules': [rule('artist', 'is', 'sleep')]}) == 1
    assert c.smartPreviewCount({'rules': [], 'limit': 2}) == 2
    c.deleteSmartPlaylist(sid)
    assert c.smartPlaylists() == []
    assert len(changed) == 3
    assert c.smartPlaylistDefinition(sid)['rules'] == []


# --- opening files from outside -------------------------------------------------------------

def test_opening_a_folder_plays_its_audio_in_natural_order(c, tmp_path):
    album = tmp_path / 'Album'
    (album / 'CD2').mkdir(parents=True)
    for name in ('10 b.flac', '2 a.flac', 'cover.jpg', 'CD2/1 c.mp3'):
        (album / name).write_bytes(b'')
    c.openPaths([str(album)])
    assert [t['title'] for t in c.player.queue] == ['2 a', '10 b', '1 c']
    assert c.player.queue[0]['album_id'] == -1


def test_opening_a_playlist_uses_the_library_for_what_it_knows(c, tmp_path):
    (tmp_path / 'list.m3u').write_text('/music/1/1.flac\n')
    c.openPaths(['file://' + str(tmp_path / 'list.m3u')])
    [track] = c.player.queue
    assert track['title'] == 'Worlds Apart' and track['album_id'] == 1


def test_opening_nothing_playable_says_so(c, tmp_path):
    (tmp_path / 'notes.txt').write_text('hi')
    c.openPaths([str(tmp_path / 'notes.txt')])
    assert c.player.queue == []
    assert 'Nothing playable' in c.notice


# --- playback settings ----------------------------------------------------------------------

def test_fade_on_pause_is_applied_and_remembered(c, con):
    from lpdeck import qmlapp
    assert c.player.backend.fade_ms == 0
    c.setFadeOnPause(True)
    assert c.player.backend.fade_ms == qmlapp.FADE_ON_PAUSE_MS
    again = _controller(con)
    assert again.fadeOnPause and again.player.backend.fade_ms == qmlapp.FADE_ON_PAUSE_MS


def test_audio_device_is_listed_applied_and_remembered(c, con):
    devices = c.outputDevices()
    assert devices[0] == {'id': '', 'name': 'System default'}
    assert {'id': 'hdmi', 'name': 'HDMI'} in devices
    c.setOutputDevice('hdmi')
    assert c.player.backend._device == 'hdmi'
    assert _controller(con).player.backend._device == 'hdmi'
    c.setOutputDevice('')
    assert c.player.backend._device is None and c.outputDevice == ''


# --- desktop --------------------------------------------------------------------------------

class FakeInhibitor:
    def __init__(self):
        self.calls = []

    def set_active(self, on):
        self.calls.append(on)


class FakeDesktop:
    available = True

    def __init__(self):
        self.visible = None
        self.notes = []

    def set_visible(self, on):
        self.visible = on

    def set_tooltip(self, text):
        pass

    def notify(self, title, body, icon_path=None):
        self.notes.append((title, body))


def test_keep_awake_follows_playback(c):
    inh = FakeInhibitor()
    c.attach_desktop(None, inh)
    c.player.backend.playing = True
    c._update_awake()
    assert inh.calls[-1] is True
    c.setKeepAwake(False)
    assert inh.calls[-1] is False
    c.setKeepAwake(True)
    c.player.backend.playing = False
    c._update_awake()
    assert inh.calls[-1] is False


def test_close_to_tray_needs_a_tray(c):
    c.attach_desktop(None, FakeInhibitor())
    c.setCloseToTray(True)
    assert not c.trayAvailable and not c.closeToTray
    desktop = FakeDesktop()
    c.attach_desktop(desktop, FakeInhibitor())
    assert desktop.visible is True and c.closeToTray
    c.setShowTray(False)
    assert desktop.visible is False and not c.closeToTray


def test_track_notifications(c, monkeypatch):
    from lpdeck import qmlapp

    class NowTimer:
        @staticmethod
        def singleShot(ms, fn):
            fn()
    monkeypatch.setattr(qmlapp, 'QTimer', NowTimer)
    desktop = FakeDesktop()
    c.attach_desktop(desktop, FakeInhibitor())
    track = {'path': '/music/1/1.flac', 'title': 'Worlds Apart', 'artist': 'Pallbearer',
             'album_name': 'Foundations of Burden', 'album_path': None}
    c.player.set_queue([track])
    c.player.backend.playing = True

    c._schedule_notification(track)            # off by default
    assert desktop.notes == []
    c.setNotifyTrackChange(True)
    c._schedule_notification(track)
    c._schedule_notification(track)            # the same track isn't announced twice
    assert desktop.notes == [('Worlds Apart', 'Pallbearer · Foundations of Burden')]

    paused = dict(track, path='/music/1/2.flac', title='The Ghost I Used to Be')
    c.player.set_queue([paused])
    c.player.backend.playing = False
    c._schedule_notification(paused)           # a paused (restored) session stays quiet
    assert len(desktop.notes) == 1
