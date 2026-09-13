"""Tests for fading on pause and choosing the audio device, on a real libVLC with
its dummy audio output.

    .venv/bin/python -m pytest tests/test_player_fade_device.py
"""
import os
import sys
import time
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


def _wav(path, seconds=20.0, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(b"\x80" * int(seconds * rate))
    return str(path)


def _wait(predicate, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.03)
    return predicate()


@pytest.fixture
def backend():
    b = PlayerBackend(audio_output="dummy")
    yield b
    b.shutdown()


@pytest.fixture
def playing(backend, tmp_path):
    files = [_wav(tmp_path / "01.wav"), _wav(tmp_path / "02.wav")]
    backend.play_tracks(files, durations=[20.0, 20.0])
    assert _wait(backend.is_actively_playing)
    return backend


def _record_volume(backend):
    levels = []
    real = backend.player.audio_set_volume

    def spy(level):
        levels.append(level)
        return real(level)
    backend.player.audio_set_volume = spy
    return levels


def _record_events(backend):
    seen = []
    for name in ("paused", "resumed"):
        backend.on(name, lambda name=name: seen.append(name))
    return seen


def test_fade_ramps_down_pauses_and_brings_the_volume_back(playing):
    backend = playing
    backend.set_volume(80)
    backend.fade_ms = 150
    levels = _record_volume(backend)
    events = _record_events(backend)

    backend.toggle_pause()
    assert events == ["paused"]                # announced at once, for the scrobbler
    assert _wait(lambda: not backend.is_actively_playing() and backend._fade_target is None)
    assert levels[-1] == 80                    # ready for the resume
    ramp = levels[:-1]
    assert ramp == sorted(ramp, reverse=True) and ramp[-1] == 0 and len(ramp) > 3

    levels.clear()
    backend.toggle_pause()
    assert events == ["paused", "resumed"]
    assert _wait(lambda: backend.is_actively_playing() and backend._fade_target is None)
    assert levels[0] == 0 and levels[-1] == 80
    assert levels[1:] == sorted(levels[1:])


def test_pausing_and_resuming_quickly_ends_up_playing(playing):
    backend = playing
    backend.fade_ms = 200
    backend.toggle_pause()
    backend.toggle_pause()                     # before the fade-out finished
    assert _wait(lambda: backend._fade_target is None)
    time.sleep(0.2)
    assert backend.is_actively_playing()


def test_explicit_pause_mid_fade_is_not_repeated(playing):
    backend = playing
    backend.fade_ms = 200
    events = _record_events(backend)
    backend.set_paused(True)
    backend.set_paused(True)                   # already heading there
    assert events == ["paused"]
    assert _wait(lambda: not backend.is_actively_playing() and backend._fade_target is None)
    backend.set_paused(True)
    assert events == ["paused"]


def test_output_devices_and_choosing_one(playing):
    backend = playing
    devices = backend.output_devices()
    assert isinstance(devices, list)
    assert all(isinstance(d, tuple) and len(d) == 2 for d in devices)
    backend.set_output_device("no-such-device")   # unknown ids don't break playback
    assert backend.output_device == "no-such-device"
    assert backend.is_actively_playing()
    backend.set_output_device(None)
    assert backend.output_device is None
