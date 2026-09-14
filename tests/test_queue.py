"""Tests for the kiosk's album queue (lp.queue) and its API.

The rules: "Play next" while a record is on lines the album up; the same
request with nothing playing just plays it; the album ends and the next one
starts; stop empties the queue; an album the queue starts is noted for
Recently played the same way a tapped one is. Player and library are stubs.

    .venv/bin/python -m pytest tests/test_queue.py
"""
import os
import sys
import threading

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lp.api import create_app
from lp.queue import QUEUE_LIMIT, AlbumQueue
from lp.state import UserState


class _Album:
    def __init__(self, artist, name):
        self.artist, self.name = artist, name
        self.folder_name = name
        self.display_name = f'{artist} - {name}'
        self.path = f'/music/{artist}/{name}'
        self.cover_path = None


ALBUMS = [_Album('Pallbearer', 'Forgotten Days'), _Album('Pallbearer', 'Heartless'),
          _Album('Sleep', 'Dopesmoker')]
BY_PATH = {a.path: a for a in ALBUMS}


class _Library:
    albums_by_path = {}

    def get_album_by_path(self, path):
        return BY_PATH.get(path)

    def get_album_tracks(self, path):
        return ['01.flac', '02.flac']


class _Player:
    def __init__(self):
        self.playing = False
        self.calls = []
        self.callbacks = {}
        self.started = threading.Event()

    def on(self, event, cb):
        self.callbacks.setdefault(event, []).append(cb)

    def fire(self, event):
        for cb in list(self.callbacks.get(event, [])):
            cb()

    def play_album(self, path, start=0):
        self.calls.append(path)
        self.playing = True
        self.started.set()

    def stop(self):
        self.playing = False
        self.fire('stop')

    def get_status(self):
        return {'playing': self.playing, 'artist': None, 'album': None}

    def end_album(self):
        """The last track finished: what libVLC's list-end event does."""
        self.playing = False
        self.started.clear()
        self.fire('album_end')
        assert self.started.wait(5) or not self.playing


@pytest.fixture
def player():
    return _Player()


def test_queueing_while_idle_just_plays(player):
    q = AlbumQueue(player, _Library())
    assert q.add(ALBUMS[0].path) == 'playing'
    assert player.calls == [ALBUMS[0].path]
    assert q.items() == []


def test_queued_albums_play_in_order_when_each_ends(player):
    q = AlbumQueue(player, _Library())
    q.add(ALBUMS[0].path)
    assert q.add(ALBUMS[1].path) == 'queued'
    assert q.add(ALBUMS[2].path) == 'queued'
    assert [i['name'] for i in q.items()] == ['Heartless', 'Dopesmoker']
    assert q.summary() == {'count': 2, 'next': q.items()[0]}

    player.end_album()
    assert player.calls[-1] == ALBUMS[1].path
    assert [i['name'] for i in q.items()] == ['Dopesmoker']
    player.end_album()
    assert player.calls[-1] == ALBUMS[2].path
    assert q.items() == []
    player.end_album()                      # nothing left: silence, no crash
    assert len(player.calls) == 3


def test_stop_empties_the_queue(player):
    q = AlbumQueue(player, _Library())
    q.add(ALBUMS[0].path)
    q.add(ALBUMS[1].path)
    player.stop()
    assert q.items() == []
    assert q.summary() == {'count': 0, 'next': None}


def test_remove_and_limits(player):
    q = AlbumQueue(player, _Library())
    q.add(ALBUMS[0].path)
    q.add(ALBUMS[1].path)
    q.add(ALBUMS[2].path)
    assert q.remove(0) is True
    assert [i['name'] for i in q.items()] == ['Dopesmoker']
    assert q.remove(5) is False
    with pytest.raises(ValueError, match='not in library'):
        q.add('/music/nope')
    for _ in range(QUEUE_LIMIT - 1):
        q.add(ALBUMS[1].path)
    with pytest.raises(ValueError, match='full'):
        q.add(ALBUMS[1].path)


def test_an_album_the_queue_starts_counts_as_recently_played_once_a_song_ends(player, tmp_path):
    state = UserState(str(tmp_path / 'state.json'))
    client = TestClient(create_app(player, _Library(), '/nonexistent', state=state))
    client.post('/api/play', json={'path': ALBUMS[0].path})
    player.fire('track_change')
    r = client.post('/api/queue', json={'path': ALBUMS[1].path})
    assert r.status_code == 200 and r.json()['status'] == 'queued'
    assert client.get('/api/status').json()['queue']['next']['name'] == 'Heartless'

    player.end_album()
    recent = [e['folder'] for e in state.get_recent_albums()]
    assert recent == ['Forgotten Days'], 'Heartless has not completed a song yet'
    player.fire('track_change')
    assert [e['folder'] for e in state.get_recent_albums()] == ['Heartless', 'Forgotten Days']


def test_queue_endpoints(player):
    client = TestClient(create_app(player, _Library(), '/nonexistent'))
    assert client.post('/api/queue', json={'path': ALBUMS[0].path}).json()['status'] == 'playing'
    client.post('/api/queue', json={'path': ALBUMS[1].path})
    client.post('/api/queue', json={'path': ALBUMS[2].path})
    assert [a['name'] for a in client.get('/api/queue').json()] == ['Heartless', 'Dopesmoker']
    assert client.post('/api/queue', json={'path': '/music/nope'}).status_code == 400
    assert client.delete('/api/queue/0').json()['queue'][0]['name'] == 'Dopesmoker'
    assert client.delete('/api/queue/7').status_code == 404
    assert client.post('/api/queue/clear').json() == {'queue': []}
    assert client.get('/api/status').json()['queue'] == {'count': 0, 'next': None}
    client.post('/api/queue', json={'path': ALBUMS[1].path})
    client.post('/api/stop')
    assert client.get('/api/queue').json() == []
