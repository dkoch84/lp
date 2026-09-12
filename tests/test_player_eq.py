"""Tests for the equalizer path in lpcore.player, and a canary on the python-vlc
bug that forces its shape.

WHY THIS FILE EXISTS
--------------------
PlayerBackend.set_equalizer always builds an EMPTY equalizer and sets the amps
itself, and the preset curves live in the app layer instead of being looked up
from libVLC. That looks like a gratuitous reimplementation until you know that
`vlc.AudioEqualizer(i)` is not a preset constructor at all.

python-vlc's `_Ctype.__new__` treats a lone int as an internal RAW C POINTER and
hands it to `_Constructor`, which does `ctypes.c_void_p(ptr)`. So:

  * AudioEqualizer(0) -> None          (_Constructor's `ptr == 0` guard)
  * AudioEqualizer(1) -> an object wrapping memory address 0x1, and the first
    method call on it dereferences address 1 and segfaults.

The real preset API is the module-level `libvlc_audio_equalizer_new_from_preset`,
which works fine. The tests below pin all of that down, so if a future python-vlc
changes the behaviour the canaries fail and the workaround can be revisited.

They never CALL a method on a bogus-pointer object; doing so would take the test
run down with a SIGSEGV. Only the wrapped address is inspected.

No PlayerBackend is instantiated here: that would build a libVLC instance and
open an audio device. eq_bands() is a staticmethod, so it needs no player.

    .venv/bin/python -m pytest tests/test_player_eq.py
"""
import ctypes
import os
import sys

import pytest
import vlc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.player import PlayerBackend


# --- what we rely on ------------------------------------------------------

def test_eq_bands_reports_libvlcs_band_centres():
    bands = PlayerBackend.eq_bands()
    assert len(bands) == 10, f"libVLC changed its band count: {bands}"
    assert bands == sorted(bands), "bands are not in ascending frequency order"
    assert all(b > 0 for b in bands)


def test_empty_equalizer_ctor_is_usable():
    """The path set_equalizer actually takes."""
    eq = vlc.AudioEqualizer()
    assert eq is not None
    assert eq.set_preamp(3.0) == 0
    assert eq.set_amp_at_index(2.0, 0) == 0
    assert eq.get_preamp() == pytest.approx(3.0)
    assert eq.get_amp_at_index(0) == pytest.approx(2.0)


def test_module_level_new_from_preset_is_the_working_preset_api():
    """The correct route, if the app ever wants libVLC's own curves instead of
    its hand-rolled ones."""
    assert vlc.libvlc_audio_equalizer_get_preset_count() > 0
    eq = vlc.libvlc_audio_equalizer_new_from_preset(0)
    assert eq is not None
    assert eq.get_preamp() == pytest.approx(eq.get_preamp())  # usable, no crash


# --- canaries on the upstream bug -----------------------------------------
#
# If either of these FAILS, python-vlc has changed. Re-read set_equalizer in
# lpcore/player.py: the hand-built-equalizer workaround may no longer be needed.

def test_canary_preset_ctor_with_index_zero_still_returns_none():
    assert vlc.AudioEqualizer(0) is None, (
        "python-vlc changed: AudioEqualizer(0) now returns an object. "
        "Re-check the workaround in lpcore.player.set_equalizer."
    )


def test_canary_preset_ctor_still_wraps_the_int_as_a_raw_pointer():
    """AudioEqualizer(1) is NOT preset 1: it is a wrapper around address 0x1.
    Only the address is read here; calling a method on it would segfault."""
    eq = vlc.AudioEqualizer(1)
    assert eq is not None
    assert ctypes.cast(eq, ctypes.c_void_p).value == 1, (
        "python-vlc changed: AudioEqualizer(int) no longer wraps the int as a "
        "pointer. Re-check the workaround in lpcore.player.set_equalizer."
    )


def test_canary_preset_ctor_is_not_equivalent_to_new_from_preset():
    """The whole point: the class ctor and the module function disagree, and
    only the module function is real."""
    real = vlc.libvlc_audio_equalizer_new_from_preset(1)
    bogus = vlc.AudioEqualizer(1)
    assert real is not None
    assert ctypes.cast(real, ctypes.c_void_p).value != 1
    assert ctypes.cast(bogus, ctypes.c_void_p).value == 1
