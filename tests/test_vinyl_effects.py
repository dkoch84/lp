"""Tests for Vinyl Effects: finishes (glass, deep edge, rim light) applied over
any style.

An effect changes the plastic, never the pattern: it must work on every style
except clear, leave the label alone, and depend only on distance from the
centre so it looks the same at every angle as the record spins. With no effects
chosen, a record must render exactly as before effects existed.

    .venv/bin/python -m pytest tests/test_vinyl_effects.py
"""
import os
import sys

import numpy as np
import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.vinyl.catalog import LABEL_RADIUS, VINYL_EFFECTS
from lpcore.vinyl.effects import apply_effects, normalize_effects
from lpcore.vinyl.render import VinylRenderer
from lpcore.vinyl.settings import VinylSettings

SIZE = 60
ALBUM = '/lp-test/album'


@pytest.fixture(scope='module', autouse=True)
def _pygame():
    pygame.init()


def _flat_disc(rgb=(40, 120, 110)):
    surf = pygame.Surface((SIZE * 2, SIZE * 2), pygame.SRCALPHA)
    pygame.draw.circle(surf, (*rgb, 255), (SIZE, SIZE), SIZE)
    return surf


def _rgb(surf):
    return pygame.surfarray.array3d(surf).astype(int)


def _lum_at(arr, x, y):
    return arr[x, y] @ np.array([299, 587, 114]) / 1000


# --- ids and validation -----------------------------------------------------------

def test_the_first_three_effects():
    assert list(VINYL_EFFECTS) == ['glass', 'deep-edge', 'rim-light']


def test_normalize_orders_and_dedupes():
    assert normalize_effects(['rim-light', 'glass', 'glass']) == ['glass', 'rim-light']


@pytest.mark.parametrize('bad', ['glass', ['sparkle'], None, 3])
def test_normalize_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        normalize_effects(bad)


def test_settings_default_to_no_effects():
    assert VinylSettings().effects == []


def test_settings_validate_and_order_effects():
    s = VinylSettings().update(effects=['rim-light', 'deep-edge'])
    assert s.effects == ['deep-edge', 'rim-light']
    with pytest.raises(ValueError):
        VinylSettings().update(effects=['sparkle'])
    with pytest.raises(ValueError):
        VinylSettings().update(effects='glass')


def test_settings_round_trip_through_a_dict():
    """lp-deck stores settings as JSON; effects must survive it."""
    s = VinylSettings().update(effects=['glass'])
    assert VinylSettings.from_dict(s.to_dict()).effects == ['glass']


# --- what each effect does ----------------------------------------------------------

def test_no_effects_changes_nothing():
    surf = _flat_disc()
    before = _rgb(surf)
    apply_effects(surf, [])
    assert (_rgb(surf) == before).all()


def test_glass_lifts_the_colour_everywhere():
    surf = _flat_disc()
    before = _rgb(surf)
    apply_effects(surf, ['glass'])
    after = _rgb(surf)
    assert _lum_at(after, SIZE, SIZE // 2) > _lum_at(before, SIZE, SIZE // 2)


def test_deep_edge_darkens_the_rim_not_the_middle():
    surf = _flat_disc()
    before = _rgb(surf)
    apply_effects(surf, ['deep-edge'])
    after = _rgb(surf)
    mid = (SIZE, SIZE - SIZE // 2)              # half way out
    rim = (SIZE, 2)                             # just inside the edge
    assert (after[mid] == before[mid]).all()
    assert _lum_at(after, *rim) < _lum_at(before, *rim)


def test_rim_light_brightens_only_the_edge():
    """The rim is a fraction of the radius wide, so it needs a record-sized disc
    to cover whole pixels (the kiosk draws at several hundred pixels)."""
    big = 400
    surf = pygame.Surface((big * 2, big * 2), pygame.SRCALPHA)
    pygame.draw.circle(surf, (40, 120, 110, 255), (big, big), big)
    before = _rgb(surf)
    apply_effects(surf, ['rim-light'])
    after = _rgb(surf)
    assert _lum_at(after, big, 1) > _lum_at(before, big, 1)
    assert (after[big, big // 2] == before[big, big // 2]).all()


@pytest.mark.parametrize('effect', list(VINYL_EFFECTS))
def test_effects_look_the_same_at_every_angle(effect):
    """The disc spins under a fixed light, so an effect may depend on radius only:
    points at the same radius on a flat disc must come out the same."""
    surf = _flat_disc()
    apply_effects(surf, [effect])
    arr = _rgb(surf)
    r = SIZE - 3
    points = [(SIZE + r, SIZE), (SIZE - r, SIZE), (SIZE, SIZE + r), (SIZE, SIZE - r)]
    values = [tuple(arr[x - 1 if x > SIZE else x, y - 1 if y > SIZE else y]) for x, y in points]
    assert len(set(values)) == 1, values


# --- applied to real records ------------------------------------------------------------

def _record(style, effects=()):
    r = VinylRenderer(VinylSettings(style=style, label='label-white', label_text='none',
                                    effects=list(effects)))
    return _rgb(r.build_record(SIZE, [0.0, 60.0, 130.0], 200.0, None, ALBUM))


@pytest.mark.parametrize('style', ['black', 'color-teal', 'nebula-marble'])
def test_effects_change_the_record_face(style):
    assert (_record(style, VINYL_EFFECTS) != _record(style)).any()


def test_clear_vinyl_takes_no_effects():
    assert (_record('clear', VINYL_EFFECTS) == _record('clear')).all()


def test_effects_leave_the_label_alone():
    plain, finished = _record('color-teal'), _record('color-teal', VINYL_EFFECTS)
    x, y = SIZE + int(SIZE * LABEL_RADIUS * 0.5), SIZE
    assert (plain[x, y] == finished[x, y]).all()


def test_no_effects_renders_as_before():
    """Default settings must not touch the record at all."""
    r = VinylRenderer(VinylSettings(style='color-teal', label_text='none'))
    before = _rgb(r.build_record(SIZE, [0.0, 60.0], 200.0, None, ALBUM))
    r.settings.effects = []
    assert (_rgb(r.build_record(SIZE, [0.0, 60.0], 200.0, None, ALBUM)) == before).all()


# --- kiosk API ----------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    from lp.api import create_app

    class _Library:
        albums_by_path = {}

    settings = VinylSettings()
    return TestClient(create_app(object(), _Library(), str(tmp_path), settings=settings)), settings


def test_api_lists_the_effects_and_none_chosen(client):
    c, _settings = client
    body = c.get('/api/settings/effects').json()
    assert body['effects'] == []
    assert [o['id'] for o in body['options']] == ['glass', 'deep-edge', 'rim-light']
    assert [o['label'] for o in body['options']] == ['Glass', 'Deep edge', 'Rim light']


def test_api_sets_effects_on_the_shared_settings(client):
    c, settings = client
    r = c.post('/api/settings/effects', json={'effects': ['rim-light', 'glass']})
    assert r.status_code == 200 and r.json()['effects'] == ['glass', 'rim-light']
    assert settings.effects == ['glass', 'rim-light']      # what the display reads
    assert c.post('/api/settings/effects', json={'effects': []}).json()['effects'] == []


def test_api_rejects_unknown_effects(client):
    c, settings = client
    c.post('/api/settings/effects', json={'effects': ['glass']})
    r = c.post('/api/settings/effects', json={'effects': ['sparkle']})
    assert r.status_code == 400
    assert settings.effects == ['glass']


# --- groove treatments ------------------------------------------------------------------

from lpcore.vinyl import catalog  # noqa: E402
from lpcore.vinyl.render import _auto_colour_groove  # noqa: E402

BOUNDS, DUR = [0.0, 60.0, 130.0], 200.0


def _grooves(style, grooves='auto', size=SIZE):
    r = VinylRenderer(VinylSettings(style=style, grooves=grooves))
    st = r.get_vinyl_style(ALBUM)
    surf, blend = r.build_grooves_overlay(size, st, BOUNDS, DUR)
    rgba = np.dstack([pygame.surfarray.array3d(surf), pygame.surfarray.array_alpha(surf)])
    return rgba, blend


def test_groove_treatments_and_default():
    assert list(catalog.GROOVE_TREATMENTS) == ['auto', 'shine', 'shadow', 'smooth']
    assert VinylSettings().grooves == 'auto'
    with pytest.raises(ValueError):
        VinylSettings().update(grooves='sparkly')
    assert VinylSettings.from_dict(VinylSettings(grooves='smooth').to_dict()).grooves == 'smooth'


def test_old_saved_settings_without_grooves_load_as_auto():
    """lp-deck rows written before grooves existed have no 'grooves' key."""
    assert VinylSettings.from_dict({'style': 'black', 'effects': []}).grooves == 'auto'


@pytest.mark.parametrize('style', ['black', 'color-cream', 'color-navy', 'nebula-marble', 'clear'])
def test_shine_is_additive_white_on_any_style(style):
    """Shine forces the faint white grooves that patterned discs get on auto.
    (The overlay stores colour scaled by alpha, so compare whole overlays
    rather than expecting pure white pixels.)"""
    rgba, blend = _grooves(style, 'shine')
    white, white_blend = _grooves('nebula-marble', 'auto')
    assert blend == white_blend == 'add'
    assert rgba[..., 3].max() > 0
    assert (rgba == white).all()


@pytest.mark.parametrize('style', ['black', 'color-navy', 'nebula-marble', 'clear'])
def test_shadow_is_a_dark_haze_on_any_style(style):
    rgba, blend = _grooves(style, 'shadow')
    drawn = rgba[..., 3] > 0
    assert blend == 'blend' and drawn.any()
    assert (rgba[drawn][:, :3] == 0).all()


@pytest.mark.parametrize('style', ['black', 'color-navy', 'nebula-marble', 'clear'])
def test_smooth_draws_no_grooves(style):
    rgba, _blend = _grooves(style, 'smooth')
    assert rgba[..., 3].max() == 0


def test_auto_is_what_styles_always_drew():
    """auto must match a renderer that has never heard of treatments; the full
    before/after render fingerprint covers every style, this pins a few."""
    for style in ('black', 'color-cream', 'color-navy', 'nebula-marble', 'clear'):
        rgba, blend = _grooves(style)
        r = VinylRenderer(VinylSettings(style=style))
        surf, want_blend = r.build_grooves_overlay(SIZE, r.get_vinyl_style(ALBUM), BOUNDS, DUR)
        assert blend == want_blend
        assert (rgba[..., 3] == pygame.surfarray.array_alpha(surf)).all()


def test_auto_rule_agrees_with_every_built_in_colour():
    for name, rgb in catalog.VINYL_COLORS.items():
        table_shines = catalog.VINYL_GROOVE_COLORS[name][0] > 128
        rule_shines = _auto_colour_groove(rgb)[0] > 128
        assert table_shines == rule_shines, name


def test_auto_picks_by_brightness_for_a_colour_without_a_table_entry(monkeypatch):
    monkeypatch.setitem(catalog.VINYL_COLORS, 'test-dark', (20, 30, 40))
    monkeypatch.setitem(catalog.VINYL_COLORS, 'test-light', (230, 225, 210))
    _rgba, dark_blend = _grooves('color-test-dark')
    _rgba, light_blend = _grooves('color-test-light')
    assert dark_blend == 'add'
    assert light_blend == 'blend'


def test_api_sets_and_validates_grooves(client):
    c, settings = client
    body = c.get('/api/settings/effects').json()
    assert body['grooves'] == 'auto'
    assert [o['label'] for o in body['groove_options']] == ['Auto', 'Shine', 'Shadow', 'Smooth']
    r = c.post('/api/settings/effects', json={'grooves': 'shadow'})
    assert r.status_code == 200 and r.json()['grooves'] == 'shadow'
    assert settings.grooves == 'shadow'


def test_api_applies_nothing_when_any_value_is_bad(client):
    c, settings = client
    r = c.post('/api/settings/effects', json={'effects': ['glass'], 'grooves': 'sparkly'})
    assert r.status_code == 400
    assert settings.effects == [] and settings.grooves == 'auto'
