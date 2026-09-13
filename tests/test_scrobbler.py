"""Tests for the Last.fm scrobbler's timing.

A track is scrobbled once half of it (or four minutes) has been heard. Paused
time used to count, so pausing a record for dinner scrobbled it; and queue
edits were treated as track changes, which could scrobble the same track twice.

    .venv/bin/python -m pytest tests/test_scrobbler.py
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore import scrobbler as scrobbler_mod
from lpcore.scrobbler import Scrobbler


class FakePlayer:
    def __init__(self):
        self._lock = threading.Lock()
        self.album = ["/music/a.flac", "/music/b.flac"]
        self.track_durations = [200.0, 200.0]
        self.current_song_index = 0
        self.callbacks = {}

    def on(self, event, cb):
        self.callbacks.setdefault(event, []).append(cb)

    def fire(self, event):
        for cb in self.callbacks.get(event, []):
            cb()

    def get_song_metadata(self, path):
        return {"artist": "Artist", "title": os.path.basename(path), "album": "Album"}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _scrobbler(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(scrobbler_mod.time, "monotonic", clock)
    player = FakePlayer()
    s = Scrobbler(player, {})
    submitted = []
    monkeypatch.setattr(s, "_do_scrobble", lambda track: submitted.append(track["title"]))
    monkeypatch.setattr(s, "_do_now_playing", lambda track: None)
    return s, player, clock, submitted


def test_queue_edits_are_not_listened_to(monkeypatch):
    _s, player, _clock, _submitted = _scrobbler(monkeypatch)
    assert "queue_change" not in player.callbacks
    assert "paused" in player.callbacks and "resumed" in player.callbacks


def test_heard_time_counts(monkeypatch):
    s, player, clock, submitted = _scrobbler(monkeypatch)
    player.fire("play_start")
    clock.now += 120                         # past half of 200 s
    player.current_song_index = 1
    player.fire("track_change")
    assert submitted == ["a.flac"]


def test_paused_time_does_not_count(monkeypatch):
    s, player, clock, submitted = _scrobbler(monkeypatch)
    player.fire("play_start")
    clock.now += 30
    player.fire("paused")
    clock.now += 3600                        # an hour paused
    player.fire("resumed")
    clock.now += 30                          # 60 s heard in total
    player.current_song_index = 1
    player.fire("track_change")
    assert submitted == []


def test_repeated_pause_or_resume_events_are_harmless(monkeypatch):
    s, player, clock, submitted = _scrobbler(monkeypatch)
    player.fire("play_start")
    clock.now += 50
    player.fire("paused")
    player.fire("paused")
    clock.now += 500
    player.fire("resumed")
    player.fire("resumed")
    clock.now += 60                          # 110 s heard
    player.fire("stop")
    assert submitted == ["a.flac"]
