"""Tests for the scoped settings endpoints and /api/settings/looks.

    .venv/bin/python -m pytest tests/test_api_looks.py
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lp.api import create_app
from lp.looks import Looks
from lpcore.vinyl.settings import VinylSettings
from test_looks import _Player
from test_queue import ALBUMS, _Library


@pytest.fixture
def rig(tmp_path):
    settings = VinylSettings()
    player = _Player()
    looks = Looks(str(tmp_path / 'looks.json'), settings, player)
    client = TestClient(create_app(player, _Library(), '/nonexistent', settings=settings,
                                   looks=looks))
    return client, settings, player


def test_edits_default_to_the_global_scope(rig):
    client, settings, _player = rig
    assert client.post('/api/settings/vinyl', json={'style': 'clear'}).status_code == 200
    assert client.post('/api/settings/brightness', json={'brightness': 60}).status_code == 200
    assert client.post('/api/settings/colors', json={'panel_color': '#000000'}).status_code == 200
    assert settings.style == 'clear' and settings.brightness == 60
    assert client.get('/api/settings/colors').json() == {'frame_color': 'auto',
                                                          'panel_color': '#000000'}


def test_album_scope_keeps_a_look_for_the_playing_album(rig):
    client, settings, player = rig
    r = client.post('/api/settings/vinyl', json={'style': 'clear', 'scope': 'album'})
    assert r.status_code == 400, 'nothing playing'
    player.play(ALBUMS[1].path)
    st = client.get('/api/settings/looks').json()
    assert st['album'] == ALBUMS[1].path and st['album_name'] == 'Pallbearer - Heartless'
    assert st['album_has_look'] is False
    assert client.post('/api/settings/effects', json={'effects': ['glass'], 'scope': 'album'}).status_code == 200
    assert client.get('/api/settings/looks').json()['album_has_look'] is True
    assert settings.effects == ['glass']
    player.play(ALBUMS[0].path)
    assert settings.effects == []
    assert client.delete('/api/settings/looks/album').status_code == 404
    player.play(ALBUMS[1].path)
    assert client.delete('/api/settings/looks/album').status_code == 200
    assert settings.effects == []


def test_bad_scope_and_bad_colors_are_400(rig):
    client, _settings, _player = rig
    assert client.post('/api/settings/brightness', json={'brightness': 10, 'scope': 'x'}).status_code == 400
    assert client.post('/api/settings/colors', json={'frame_color': 'black'}).status_code == 400
