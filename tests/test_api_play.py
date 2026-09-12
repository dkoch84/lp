"""Tests for POST /api/play, including the start-at-track index.

The point: `start` reaches libVLC as a queue offset, and an out-of-range index
would either play the wrong thing or fail somewhere deep in the player. The
endpoint is the only place that can check it against the album, so these pin
down that it does, and that the index it accepts means the same track the
/tracks listing showed.

Player and library are stubs: no VLC instance, no audio device, no real music.
What is under test is the endpoint's contract, not playback.

    .venv/bin/python -m pytest tests/test_api_play.py
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lp.api import create_app

TRACKS = ["01 Forgotten Days.flac", "02 Stasis.flac", "03 Rite of Ruin.flac",
          "04 Silver Wings.flac", "05 Caledonia.flac"]
ALBUM_PATH = "/music/Pallbearer/Forgotten Days"


class _Album:
    artist = "Pallbearer"
    folder_name = "Forgotten Days"
    display_name = "Pallbearer - Forgotten Days"
    path = ALBUM_PATH


class _Library:
    # create_app prewarms cover thumbnails from this on startup.
    albums_by_path = {}

    def get_album_by_path(self, path):
        return _Album() if path == ALBUM_PATH else None

    def get_album_tracks(self, path):
        return list(TRACKS) if path == ALBUM_PATH else []


class _Player:
    """Records what play_album was asked to do."""

    def __init__(self):
        self.calls = []

    def play_album(self, album_path, start=0):
        self.calls.append((album_path, start))

    def stop(self):
        self.calls.append(("stop", None))

    def get_status(self):
        return {"playing": False}


@pytest.fixture
def client(tmp_path):
    player = _Player()
    app = create_app(player, _Library(), str(tmp_path))
    c = TestClient(app)
    c.player = player
    return c


def test_play_without_start_begins_at_the_top(client):
    r = client.post("/api/play", json={"path": ALBUM_PATH})
    assert r.status_code == 200
    assert client.player.calls == [(ALBUM_PATH, 0)]


def test_play_passes_the_start_index_through(client):
    r = client.post("/api/play", json={"path": ALBUM_PATH, "start": 4})
    assert r.status_code == 200
    assert client.player.calls == [(ALBUM_PATH, 4)]


def test_start_index_addresses_the_same_track_the_listing_showed(client):
    """The sheet sends the row index; it has to mean that row. Both the API and
    the player sort the directory listing, so index 2 is the third file."""
    listing = _Library().get_album_tracks(ALBUM_PATH)
    assert listing == sorted(listing), "listing is not sorted; indexes would not line up"
    assert listing[2] == "03 Rite of Ruin.flac"

    client.post("/api/play", json={"path": ALBUM_PATH, "start": 2})
    assert client.player.calls == [(ALBUM_PATH, 2)]


@pytest.mark.parametrize("start", [5, 6, 99, -1, -10])
def test_out_of_range_start_is_rejected_and_plays_nothing(client, start):
    r = client.post("/api/play", json={"path": ALBUM_PATH, "start": start})
    assert r.status_code == 400
    assert "out of range" in r.json()["detail"]
    assert client.player.calls == [], "rejected request still started playback"


def test_last_track_is_in_range(client):
    """The off-by-one that matters: finishing an album from its final track."""
    r = client.post("/api/play", json={"path": ALBUM_PATH, "start": len(TRACKS) - 1})
    assert r.status_code == 200
    assert client.player.calls == [(ALBUM_PATH, len(TRACKS) - 1)]


def test_unknown_album_is_rejected_before_the_start_check(client):
    r = client.post("/api/play", json={"path": "/music/Nope"})
    assert r.status_code == 400
    assert "not in library" in r.json()["detail"]
    assert client.player.calls == []


def test_start_defaults_to_zero_when_omitted(client):
    """Existing clients post {path} alone and must keep working."""
    r = client.post("/api/play", json={"path": ALBUM_PATH})
    assert r.status_code == 200
    assert client.player.calls[0][1] == 0


def test_non_integer_start_is_rejected(client):
    r = client.post("/api/play", json={"path": ALBUM_PATH, "start": "three"})
    assert r.status_code == 422
    assert client.player.calls == []
