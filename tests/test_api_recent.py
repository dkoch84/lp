"""Tests for what lands on the Recently played shelf, and taking things off it.

Pressing play is not listening: a mis-tap on the grid used to sit on the
shelf for a week. An album is recorded when its first song completes (the
player's track_change) or, for a one-track album, when it ends; stopping
before then records nothing. DELETE /api/recent/{artist}/{folder} removes an
entry by hand.

    .venv/bin/python -m pytest tests/test_api_recent.py
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lp.api import create_app
from lp.state import UserState
from test_api_play import ALBUM_PATH, _Library, _Player


class _EventPlayer(_Player):
    """The play stub plus the events the recent shelf listens for."""

    def __init__(self):
        super().__init__()
        self.callbacks = {}

    def on(self, event, cb):
        self.callbacks.setdefault(event, []).append(cb)

    def fire(self, event):
        for cb in self.callbacks.get(event, []):
            cb()


@pytest.fixture
def rig(tmp_path):
    player = _EventPlayer()
    state = UserState(str(tmp_path / 'state.json'))
    client = TestClient(create_app(player, _Library(), '/nonexistent', state=state))
    return client, player, state


def _recent(state):
    return [(e['artist'], e['folder']) for e in state.get_recent_albums()]


def test_pressing_play_alone_records_nothing(rig):
    client, player, state = rig
    assert client.post('/api/play', json={'path': ALBUM_PATH}).status_code == 200
    assert _recent(state) == []
    assert state.get_last_played('Pallbearer') is None


def test_a_completed_song_puts_the_album_on_the_shelf(rig):
    client, player, state = rig
    client.post('/api/play', json={'path': ALBUM_PATH})
    player.fire('track_change')
    assert _recent(state) == [('Pallbearer', 'Forgotten Days')]
    assert state.get_last_played('Pallbearer') is not None
    before = state.get_recent_albums()[0]['ts']
    player.fire('track_change')          # later boundaries do not re-record
    assert state.get_recent_albums()[0]['ts'] == before


def test_a_one_track_album_counts_when_it_ends(rig):
    client, player, state = rig
    client.post('/api/play', json={'path': ALBUM_PATH})
    player.fire('album_end')
    assert _recent(state) == [('Pallbearer', 'Forgotten Days')]


def test_stopping_before_a_song_completes_records_nothing(rig):
    client, player, state = rig
    client.post('/api/play', json={'path': ALBUM_PATH})
    player.fire('stop')
    player.fire('track_change')          # a stale boundary event changes nothing
    assert _recent(state) == []


def test_removing_from_recent(rig):
    client, player, state = rig
    client.post('/api/play', json={'path': ALBUM_PATH})
    player.fire('track_change')
    r = client.delete('/api/recent/Pallbearer/Forgotten%20Days')
    assert r.status_code == 200 and r.json() == {'removed': True}
    assert _recent(state) == []
    assert client.delete('/api/recent/Pallbearer/Forgotten%20Days').status_code == 404
