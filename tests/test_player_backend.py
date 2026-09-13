"""Tests for lpcore.player.PlayerBackend's queue and metadata handling, on a real
libVLC with its dummy audio output and short generated WAV files.

These pin down slow paths and bugs found by comparing with mature players:
tags re-read from disk on every status call, blank titles for formats other
than MP3 and FLAC, every file opened for its length when the caller already
knew it, adds that did nothing in crossfade mode, adds announced as track
changes, and jumping to a row that reloaded the whole queue.

Skipped where libVLC isn't installed (like the kiosk's test box).

    .venv/bin/python -m pytest tests/test_player_backend.py
"""
import os
import sys
import wave

import pytest
import vlc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.player import PlayerBackend


def _has_libvlc():
    try:
        vlc.libvlc_get_version()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _has_libvlc(), reason="no libVLC on this host")


def _wav(path, seconds=1.0, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(b"\x80" * int(seconds * rate))
    return str(path)


@pytest.fixture
def files(tmp_path):
    return [_wav(tmp_path / f"{i:02d} track.wav") for i in range(1, 5)]


@pytest.fixture
def backend():
    b = PlayerBackend(audio_output="dummy")
    yield b
    b.shutdown()


def _events(backend):
    seen = []
    for name in ("play_start", "track_change", "queue_change"):
        backend.on(name, lambda n=name: seen.append(n))
    return seen


def test_tags_are_read_once_per_file(backend, tmp_path, monkeypatch):
    """Long tracks, so playback can't move on mid-test; and whatever track is
    playing, no file may be read twice until its cache entry is dropped."""
    long = [_wav(tmp_path / f"cache{i}.wav", seconds=20) for i in range(2)]
    reads = []
    real = backend._read_song_metadata
    monkeypatch.setattr(backend, "_read_song_metadata", lambda p: reads.append(p) or real(p))
    backend.play_tracks(long, durations=[20.0, 20.0])
    for _ in range(20):
        backend.get_status()
    assert reads == [long[0]]
    backend.invalidate_metadata(long[0])
    backend.get_status()
    assert reads == [long[0], long[0]]


def test_formats_beyond_mp3_and_flac_get_metadata(backend, files):
    """WAV here stands in for m4a/ogg/opus: all go through mutagen's generic
    loader. Before, anything but MP3/FLAC returned None and showed no title."""
    assert backend._read_song_metadata(files[0]) is not None


def test_known_durations_are_not_read_from_files(backend, files, monkeypatch):
    def no_file_reads(path):
        raise AssertionError(f"read {path} for its duration")
    monkeypatch.setattr(backend, "_get_file_duration", no_file_reads)
    backend.play_tracks(files, durations=[10.0, 20.0, 30.0, 40.0])
    assert backend.album_duration == 100.0
    assert backend.track_boundaries == [0.0, 10.0, 30.0, 60.0]


def test_missing_durations_fall_back_to_the_file(backend, files):
    backend.play_tracks(files[:2], durations=[5.0, 0])
    assert backend.track_durations[0] == 5.0
    assert backend.track_durations[1] == pytest.approx(1.0, abs=0.05)


def test_adding_tracks_keeps_known_durations_and_is_a_queue_change(backend, files, monkeypatch):
    backend.play_tracks(files[:2], durations=[10.0, 20.0])
    seen = _events(backend)
    monkeypatch.setattr(backend, "_get_file_duration",
                        lambda p: (_ for _ in ()).throw(AssertionError("re-read a duration")))
    backend.append_tracks([files[2]], durations=[30.0])
    backend.insert_tracks_next([files[3]], durations=[5.0])
    assert backend.album == [files[0], files[3], files[1], files[2]]
    assert backend.track_durations == [10.0, 5.0, 20.0, 30.0]
    assert backend.album_duration == 65.0
    assert len(backend._mrls) == 4 and backend._media_list.count() == 4
    assert "queue_change" in seen and "track_change" not in seen


def test_adding_tracks_works_in_crossfade_mode(backend, files):
    backend.set_crossfade(2000)
    backend.play_tracks(files[:2], durations=[10.0, 20.0])
    backend.append_tracks([files[2]], durations=[30.0])
    assert backend.album == files[:3]
    assert backend.album_duration == 60.0


def test_jumping_keeps_the_loaded_queue(backend, files):
    backend.play_tracks(files, durations=[1.0] * len(files))
    loaded = backend._media_list
    backend.jump_to(2)
    assert backend._media_list is loaded
    backend.jump_to(99)                      # out of range: ignored
    assert backend._media_list is loaded


def test_is_loaded(backend, files):
    assert not backend.is_loaded()
    backend.play_tracks(files[:1], durations=[1.0])
    assert backend.is_loaded()
    backend.stop()
    assert not backend.is_loaded()


def test_resume_offset_waits_for_playback_to_start(backend, files):
    backend.play_tracks(files, start=1, paused=True, start_offset=0.4,
                        durations=[1.0] * len(files))
    pending = backend._pending_start
    assert pending is None or pending[:2] == (0.4, True)


# --- editing the queue, unplayable files, stop after, previous ------------------------

def _wait(predicate, timeout=8.0):
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.03)
    return predicate()


def _now(backend):
    m = backend.player.get_media()
    return vlc.bytes_to_str(m.get_mrl()).rsplit("/", 1)[-1] if m else None


def _name(path):
    from urllib.parse import quote
    return quote(os.path.basename(path))


@pytest.fixture
def long_files(tmp_path):
    return [_wav(tmp_path / f"long{i}.wav", seconds=20) for i in range(5)]


def _playing(backend, files, index):
    backend.play_tracks(files, start=index, durations=[20.0] * len(files))
    assert _wait(lambda: backend.is_actively_playing() and _now(backend) == _name(files[index]))


def test_removing_an_upcoming_track_is_a_live_edit(backend, long_files):
    _playing(backend, long_files, 1)
    loaded = backend._media_list
    backend.remove_track(3)
    assert backend._media_list is loaded and loaded.count() == 4
    assert backend.album == [long_files[i] for i in (0, 1, 2, 4)]
    backend.next_track()
    assert _wait(lambda: _now(backend) == _name(long_files[2]))
    backend.next_track()
    assert _wait(lambda: _now(backend) == _name(long_files[4]))


def test_removing_an_earlier_track_keeps_playing_the_same_one(backend, long_files):
    _playing(backend, long_files, 2)
    backend.remove_track(0)
    assert backend.album == long_files[1:]
    assert backend.current_song_index == 1
    assert _wait(lambda: backend.is_actively_playing() and _now(backend) == _name(long_files[2]))
    backend.next_track()
    assert _wait(lambda: _now(backend) == _name(long_files[3]))


def test_removing_the_playing_track_moves_on(backend, long_files):
    _playing(backend, long_files, 1)
    backend.remove_track(1)
    assert _wait(lambda: _now(backend) == _name(long_files[2]))
    assert backend.current_song_index == 1


def test_moving_upcoming_tracks_is_a_live_edit(backend, long_files):
    _playing(backend, long_files, 1)
    loaded = backend._media_list
    backend.move_track(4, 2)
    assert backend._media_list is loaded
    assert backend.album == [long_files[i] for i in (0, 1, 4, 2, 3)]
    backend.next_track()
    assert _wait(lambda: _now(backend) == _name(long_files[4]))


def test_moving_the_playing_track_follows_it(backend, long_files):
    _playing(backend, long_files, 1)
    backend.move_track(1, 3)
    assert backend.album == [long_files[i] for i in (0, 2, 3, 1, 4)]
    assert backend.current_song_index == 3
    assert _wait(lambda: _now(backend) == _name(long_files[1]))


def test_replacing_upcoming_tracks_keeps_playback_going(backend, long_files):
    _playing(backend, long_files, 1)
    loaded = backend._media_list
    seen = _events(backend)
    backend.replace_upcoming([long_files[4], long_files[2], long_files[3]], durations=[1.0, 2.0, 3.0])
    assert backend._media_list is loaded
    assert backend.album == [long_files[i] for i in (0, 1, 4, 2, 3)]
    assert backend.track_durations[2:] == [1.0, 2.0, 3.0]
    assert "queue_change" in seen and "play_start" not in seen
    assert _now(backend) == _name(long_files[1])
    backend.next_track()
    assert _wait(lambda: _now(backend) == _name(long_files[4]))


def test_clearing_the_queue(backend, long_files):
    _playing(backend, long_files, 0)
    seen = _events(backend)
    backend.clear_queue()
    assert backend.album == [] and not backend.is_loaded()
    assert "queue_change" in seen


def test_a_missing_file_is_skipped_and_reported(backend, tmp_path):
    first = _wav(tmp_path / "first.wav", seconds=0.5)
    after = _wav(tmp_path / "after.wav", seconds=10)
    missing = str(tmp_path / "missing.wav")
    errors = []
    backend.on("track_error", lambda: errors.append(backend.last_error))
    backend.play_tracks([first, missing, after], durations=[0.5, 1.0, 10.0])
    assert _wait(lambda: _now(backend) == "after.wav" and backend.is_actively_playing(), timeout=10)
    assert errors and errors[0] == (1, missing)
    assert backend.current_song_index == 2


def test_stop_after_this_track_pauses_at_the_next_one(backend, tmp_path):
    short = _wav(tmp_path / "short.wav", seconds=0.6)
    nxt = _wav(tmp_path / "next.wav", seconds=10)
    stopped = []
    backend.on("stopped_after", lambda: stopped.append(True))
    backend.stop_after_current = True
    backend.play_tracks([short, nxt], durations=[0.6, 10.0])
    assert _wait(lambda: stopped, timeout=10)
    assert _wait(lambda: not backend.is_actively_playing())
    assert backend.current_song_index == 1
    assert backend.get_current_time() < 0.5
    assert backend.stop_after_current is False


def test_previous_restarts_a_track_a_few_seconds_in(backend, long_files):
    _playing(backend, long_files, 2)
    seeks = []
    backend.on("seeked", lambda: seeks.append(True))
    backend.seek_track(6.0)
    assert _wait(lambda: backend.get_current_time() >= 5.0)
    backend.prev_track()
    assert _wait(lambda: backend.get_current_time() < 2.0)
    assert backend.current_song_index == 2 and _now(backend) == _name(long_files[2])
    assert len(seeks) == 2
    backend.prev_track()                     # now near the start: really go back
    assert _wait(lambda: _now(backend) == _name(long_files[1]))
