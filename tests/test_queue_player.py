"""Tests for lp-deck's QueuePlayer, against a fake backend.

The queue player keeps display rows parallel to what the backend has loaded.
These pin down the bugs a mature player doesn't have: tracks added while
shuffled must survive turning shuffle off, durations the library already knows
must reach the backend (so it doesn't open every file), jumping to a row must
not reload the queue, and the session must be saved safely and as playback
happens, not only on a clean exit.

    .venv/bin/python -m pytest tests/test_queue_player.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpdeck.player import QueuePlayer


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.current_song_index = 0
        self.callbacks = {}
        self.time = 12.5

    def on(self, event, cb):
        self.callbacks.setdefault(event, []).append(cb)

    def fire(self, event):
        for cb in self.callbacks.get(event, []):
            cb()

    def play_tracks(self, files, album_path=None, start=0, paused=False,
                    start_offset=0.0, durations=None):
        self.calls.append(("play_tracks", list(files), start, list(durations or [])))
        self.current_song_index = start

    def append_tracks(self, files, durations=None):
        self.calls.append(("append_tracks", list(files), list(durations or [])))

    def insert_tracks_next(self, files, durations=None):
        self.calls.append(("insert_tracks_next", list(files), list(durations or [])))

    def jump_to(self, idx):
        self.calls.append(("jump_to", idx))
        self.current_song_index = idx

    def get_current_time(self):
        return self.time

    def set_repeat(self, mode):
        pass


def _tracks(*names):
    return [{"path": f"/music/{n}.flac", "title": n, "duration": 100.0 + i}
            for i, n in enumerate(names)]


def _paths(tracks):
    return [t["path"] for t in tracks]


def test_known_durations_reach_the_backend():
    b = FakeBackend()
    q = QueuePlayer(b)
    q.set_queue(_tracks("a", "b", "c"))
    name, files, start, durations = b.calls[-1]
    assert name == "play_tracks" and durations == [100.0, 101.0, 102.0]


def test_added_tracks_carry_their_durations():
    b = FakeBackend()
    q = QueuePlayer(b)
    q.set_queue(_tracks("a", "b"))
    q.add_tracks([{"path": "/music/x.flac", "duration": 42.0}])
    q.add_tracks([{"path": "/music/y.flac", "duration": 7.0}], play_next=True)
    assert b.calls[-2] == ("append_tracks", ["/music/x.flac"], [42.0])
    assert b.calls[-1] == ("insert_tracks_next", ["/music/y.flac"], [7.0])


def test_tracks_added_while_shuffled_survive_turning_shuffle_off():
    b = FakeBackend()
    q = QueuePlayer(b)
    q.set_queue(_tracks("a", "b", "c", "d"))
    q.set_shuffle(True)
    appended = {"path": "/music/appended.flac", "duration": 1.0}
    nexted = {"path": "/music/next.flac", "duration": 1.0}
    q.add_tracks([appended])
    q.add_tracks([nexted], play_next=True)
    q.set_shuffle(False)
    paths = _paths(q.queue)
    assert "/music/appended.flac" in paths and "/music/next.flac" in paths
    assert len(paths) == 6


def test_play_next_lands_after_the_current_track_in_natural_order():
    b = FakeBackend()
    q = QueuePlayer(b)
    q.set_queue(_tracks("a", "b", "c"), start=0)
    b.current_song_index = 1                 # now playing b
    q.add_tracks([{"path": "/music/n.flac", "duration": 1.0}], play_next=True)
    assert _paths(q.queue) == ["/music/a.flac", "/music/b.flac", "/music/n.flac", "/music/c.flac"]
    q.set_shuffle(True)
    q.set_shuffle(False)
    assert _paths(q.queue) == ["/music/a.flac", "/music/b.flac", "/music/n.flac", "/music/c.flac"]


def test_jumping_to_a_row_does_not_reload_the_queue():
    b = FakeBackend()
    q = QueuePlayer(b)
    q.set_queue(_tracks("a", "b", "c"))
    b.calls.clear()
    q.jump_to(2)
    assert b.calls == [("jump_to", 2)]
    q.jump_to(9)
    assert b.calls == [("jump_to", 2)]


def test_save_state_is_atomic_and_complete(tmp_path):
    b = FakeBackend()
    q = QueuePlayer(b)
    q.set_queue(_tracks("a", "b"), start=1)
    path = tmp_path / "session.json"
    q.save_state(str(path))
    state = json.loads(path.read_text())
    assert _paths(state["queue"]) == ["/music/a.flac", "/music/b.flac"]
    assert state["index"] == 1 and state["offset"] == 12.5
    assert not (tmp_path / "session.json.tmp").exists()


def test_save_state_failure_is_logged_not_raised(tmp_path, caplog):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    q = QueuePlayer(FakeBackend())
    q.save_state(str(blocker / "session.json"))
    assert "could not save the session" in caplog.text


def test_autosave_writes_as_playback_happens(tmp_path):
    b = FakeBackend()
    q = QueuePlayer(b)
    path = tmp_path / "session.json"
    q.enable_autosave(str(path))
    q.set_queue(_tracks("a", "b"))
    assert not path.exists()                 # nothing fired yet
    b.current_song_index = 1
    b.fire("track_change")
    assert json.loads(path.read_text())["index"] == 1
    for event in ("play_start", "stop", "queue_change"):
        assert event in b.callbacks
