"""Tests for lp.looks: the saved global look, per-album looks, and the
effective look the display reads.

    .venv/bin/python -m pytest tests/test_looks.py
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lp.looks import Looks
from lpcore.vinyl.settings import VinylSettings

A, B = '/music/Pallbearer/Heartless', '/music/Sleep/Dopesmoker'


class _Player:
    def __init__(self):
        self.album_path = None
        self.callbacks = {}

    def on(self, event, cb):
        self.callbacks.setdefault(event, []).append(cb)

    def get_status(self):
        return {'playing': self.album_path is not None}

    def play(self, path):
        self.album_path = path
        for cb in self.callbacks.get('play_start', []):
            cb()

    def stop(self):
        self.album_path = None
        for cb in self.callbacks.get('stop', []):
            cb()


@pytest.fixture
def rig(tmp_path):
    settings = VinylSettings()
    player = _Player()
    looks = Looks(str(tmp_path / 'looks.json'), settings, player)
    return looks, settings, player, tmp_path / 'looks.json'


def test_a_global_edit_shows_and_is_saved(rig):
    looks, settings, _player, path = rig
    looks.update('global', style='nebula-teal-marble', brightness=80)
    assert settings.style == 'nebula-teal-marble' and settings.brightness == 80
    saved = json.loads(path.read_text())
    assert saved['global'] == {'style': 'nebula-teal-marble', 'brightness': 80}
    assert saved['albums'] == {}


def test_the_saved_look_survives_a_restart(rig):
    looks, _settings, _player, path = rig
    looks.update('global', style='clear', effects=['glass'])
    fresh = VinylSettings()
    Looks(str(path), fresh)
    assert fresh.style == 'clear' and fresh.effects == ['glass']


def test_an_album_look_starts_from_what_is_on_screen_and_wins_while_it_plays(rig):
    looks, settings, player, path = rig
    looks.update('global', style='black', label='label-white', brightness=70)
    player.play(A)
    looks.update('album', style='nebula-teal-marble')
    assert settings.style == 'nebula-teal-marble'
    assert settings.brightness == 70, 'the album look started from the screen'
    assert looks.status()['album_has_look'] is True

    player.play(B)
    assert settings.style == 'black', 'another album gets the global look'
    assert looks.status()['album_has_look'] is False

    player.play(A)
    assert settings.style == 'nebula-teal-marble', 'the album remembers'
    saved = json.loads(path.read_text())
    assert saved['albums'][A]['style'] == 'nebula-teal-marble'
    assert saved['albums'][A]['brightness'] == 70


def test_a_global_edit_does_not_change_an_album_with_its_own_look(rig):
    looks, settings, player, _path = rig
    player.play(A)
    looks.update('album', style='clear')
    looks.update('global', style='color-red')
    assert settings.style == 'clear'
    player.stop()
    assert settings.style == 'color-red'


def test_forgetting_an_album_look(rig):
    looks, settings, player, path = rig
    player.play(A)
    looks.update('album', style='clear')
    assert looks.forget_album() is True
    assert settings.style == 'black'
    assert looks.forget_album() is False
    assert json.loads(path.read_text())['albums'] == {}


def test_album_scope_needs_something_playing(rig):
    looks, _settings, _player, _path = rig
    with pytest.raises(ValueError, match='nothing is playing'):
        looks.update('album', style='clear')
    with pytest.raises(ValueError, match='scope'):
        looks.update('everywhere', style='clear')


def test_a_bad_value_applies_nothing(rig):
    looks, settings, _player, _path = rig
    with pytest.raises(ValueError):
        looks.update('global', brightness=50, grooves='sparkly')
    assert settings.brightness == 100


def test_frame_and_panel_colors_are_looks_too(rig):
    looks, settings, _player, _path = rig
    looks.update('global', panel_color='#000000')
    assert settings.panel_color == '#000000' and settings.frame_color == 'auto'
    with pytest.raises(ValueError):
        looks.update('global', frame_color='black')


def test_preconfigured_settings_are_adopted_when_nothing_is_saved(tmp_path):
    settings = VinylSettings().update(effects=['rim-light'], grooves='shine')
    looks = Looks(str(tmp_path / 'looks.json'), settings)
    assert settings.effects == ['rim-light'] and settings.grooves == 'shine'
    assert looks.global_look == {'effects': ['rim-light'], 'grooves': 'shine'}


def test_unknown_or_stale_saved_values_are_dropped(tmp_path):
    path = tmp_path / 'looks.json'
    path.write_text(json.dumps({'global': {'style': 'clear', 'brightness': 500, 'bogus': 1},
                                'albums': {A: {'grooves': 'nope'}, B: {}}}))
    settings = VinylSettings()
    looks = Looks(str(path), settings)
    assert settings.style == 'clear' and settings.brightness == 100
    assert looks.album_looks == {A: {}}


def test_display_parses_look_colors():
    from lp.display import parse_color
    assert parse_color('#102030', (1, 1, 1)) == (16, 32, 48)
    assert parse_color('auto', (1, 1, 1)) == (1, 1, 1)
    assert parse_color('#zzzzzz', (1, 1, 1)) == (1, 1, 1)
