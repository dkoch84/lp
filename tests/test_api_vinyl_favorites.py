"""Tests for the vinyl-style favorites API.

A favorites system for vinyl styles (distinct from artist favorites): favorite
a color/fractal style, then the web UI can flip between showing all styles and
showing only favorites. The Basic category is never hidden; the colors,
mandelbrot, nebula and munafo galleries collapse to favorites in favorites mode.
The server just stores the favorited style ids; the filtering is done in the UI.

    .venv/bin/python -m pytest tests/test_api_vinyl_favorites.py
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lp.api import create_app
from lp.state import UserState
from test_api_play import _Library, _Player


@pytest.fixture
def rig(tmp_path):
    state = UserState(str(tmp_path / 'state.json'))
    client = TestClient(create_app(_Player(), _Library(), '/nonexistent', state=state))
    return client, state


def test_favorites_start_empty(rig):
    client, _ = rig
    r = client.get('/api/settings/vinyl/favorites')
    assert r.status_code == 200
    assert r.json() == {'favorites': []}


def test_favorite_then_unfavorite(rig):
    client, state = rig
    r = client.post('/api/settings/vinyl/favorites/color-red', json={'favorite': True})
    assert r.status_code == 200
    assert r.json() == {'id': 'color-red', 'favorite': True}
    assert client.get('/api/settings/vinyl/favorites').json() == {'favorites': ['color-red']}
    assert state.is_vinyl_favorite('color-red') is True

    r = client.post('/api/settings/vinyl/favorites/color-red', json={'favorite': False})
    assert r.status_code == 200
    assert client.get('/api/settings/vinyl/favorites').json() == {'favorites': []}


def test_favorites_are_sorted_and_multi(rig):
    client, _ = rig
    for sid in ['nebula-lava-lamp', 'color-teal', 'munafo-deep5_v1']:
        client.post(f'/api/settings/vinyl/favorites/{sid}', json={'favorite': True})
    assert client.get('/api/settings/vinyl/favorites').json() == {
        'favorites': ['color-teal', 'munafo-deep5_v1', 'nebula-lava-lamp']
    }


def test_favorites_persist_across_app_reload(rig, tmp_path):
    client, state = rig
    client.post('/api/settings/vinyl/favorites/color-teal', json={'favorite': True})
    # A fresh app over the same state file still sees the favorite.
    reloaded = UserState(state.path)
    client2 = TestClient(create_app(_Player(), _Library(), '/nonexistent', state=reloaded))
    assert client2.get('/api/settings/vinyl/favorites').json() == {'favorites': ['color-teal']}


def test_favorites_without_state_are_empty_not_error():
    # --no-display / test runs pass no state store; the endpoint degrades to [].
    client = TestClient(create_app(_Player(), _Library(), '/nonexistent'))
    assert client.get('/api/settings/vinyl/favorites').json() == {'favorites': []}
    # Writing without a state store is a clean 503, not a crash.
    r = client.post('/api/settings/vinyl/favorites/color-red', json={'favorite': True})
    assert r.status_code == 503
