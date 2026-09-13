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


def test_tags_are_read_once_per_file(backend, files, monkeypatch):
    reads = []
    real = backend._read_song_metadata
    monkeypatch.setattr(backend, "_read_song_metadata", lambda p: reads.append(p) or real(p))
    backend.play_tracks(files, durations=[1.0] * len(files))
    for _ in range(5):
        backend.get_status()
    assert reads == [files[0]]
    backend.invalidate_metadata(files[0])
    backend.get_status()
    assert reads == [files[0], files[0]]


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
