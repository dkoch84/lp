"""Tests for the teal-marble vinyl: translucent teal with overlapping smoke.

It is a nebula variant routed to the layered-smoke renderer (``'layers'`` as the
7th tuple element): several layers of the marble field, each rotated and
stretched its own way, stacked so crossings get darker. The routing is what can
break silently. Drop the tag and the style still renders, just as a generic
swirly nebula, and nothing else fails. So these pin the route, every style id
that reaches it, and the basic look.

    .venv/bin/python -m pytest tests/test_teal_marble.py
"""
import os
import sys

import numpy as np
import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.vinyl.fractals import (NEBULA_VARIANTS, SMOKE_LAYER_PARAMS, SMOKE_MAX_LAYERS,
                                  _render_nebula_surface)
from lpcore.vinyl.render import VinylRenderer
from lpcore.vinyl.settings import VinylSettings

NAME = 'teal-marble'
SIZE = 120
LUMA = np.array([0.299, 0.587, 0.114])


@pytest.fixture(scope='module')
def variant():
    pygame.init()
    matches = [v for v in NEBULA_VARIANTS if v[2] == NAME]
    assert len(matches) == 1, f'{NAME} missing from NEBULA_VARIANTS (or listed twice)'
    return matches[0]


@pytest.fixture(scope='module')
def pixels(variant):
    """(rgb, alpha) of a direct render, rows first."""
    surf = _render_nebula_surface(variant, SIZE)
    rgb = pygame.surfarray.array3d(surf).transpose(1, 0, 2).astype(np.float64)
    alpha = pygame.surfarray.array_alpha(surf).T.astype(np.float64)
    return rgb, alpha


def _disc(rgb, alpha):
    """Opaque pixels well inside the rim, so edge anti-aliasing does not skew
    the colour statistics."""
    n = rgb.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(xx - n / 2, yy - n / 2) / (n / 2)
    return rgb[(r < 0.9) & (alpha > 250)]


# --- wiring -----------------------------------------------------------------

def test_routes_to_the_layered_smoke_renderer(variant):
    """The regression this file exists for."""
    assert len(variant) > 6 and variant[6] == 'layers', variant[6:]


def test_style_id_resolves_to_this_variant(variant):
    style = VinylRenderer(VinylSettings(style=f'nebula-{NAME}')).get_vinyl_style('/lp-test/album')
    assert style['type'] == 'nebula'
    assert style['variant'][2] == NAME


def test_pattern_disc_form_resolves(variant):
    style = VinylRenderer(VinylSettings(style=f'pattern-nebula-{NAME}')).get_vinyl_style('/lp-test/album')
    assert style['type'] == 'pattern'
    assert style['sub']['variant'][2] == NAME


def test_offered_by_the_web_picker(tmp_path):
    from fastapi.testclient import TestClient
    from lp.api import create_app

    class _Library:
        albums_by_path = {}

    client = TestClient(create_app(object(), _Library(), str(tmp_path)))
    ids = {o['id'] for o in client.get('/api/settings/vinyl/options').json()['options']}
    assert f'nebula-{NAME}' in ids
    assert f'pattern-nebula-{NAME}' in ids


def test_renders_through_the_real_record_pipeline(variant):
    r = VinylRenderer(VinylSettings(style=f'nebula-{NAME}', label='art'))
    st = r.get_vinyl_style('/lp-test/album')
    body = r.build_record(48, [0.0, 60.0, 130.0], 200.0, None, '/lp-test/album', 'A', 'B')
    grooves, _mode = r.build_grooves_overlay(48, st, [0.0, 60.0, 130.0], 200.0)
    shine = r.build_shine_overlay(48, st)
    assert body.get_size() == grooves.get_size() == shine.get_size() == (96, 96)


# --- the renderer -------------------------------------------------------------

def test_body_is_teal(pixels):
    rgb, alpha = pixels
    body = _disc(rgb, alpha)
    r, g, b = body[:, 0].mean(), body[:, 1].mean(), body[:, 2].mean()
    assert g > r * 1.8, f'not green enough for teal: ({r:.0f},{g:.0f},{b:.0f})'
    assert b > r * 1.5, f'not blue enough for teal: ({r:.0f},{g:.0f},{b:.0f})'
    assert abs(g - b) < 45, f'drifted to plain green or blue: ({r:.0f},{g:.0f},{b:.0f})'


def test_smoke_darkens_part_of_the_disc_but_not_most_of_it(pixels):
    rgb, alpha = pixels
    lum = _disc(rgb, alpha) @ LUMA
    dark = (lum < np.median(lum) * 0.8).mean()
    assert 0.03 < dark < 0.6, f'{dark:.1%} of the disc is smoke'


def test_overlapping_layers_darken_more_than_one(variant):
    """Transmittance stacking: more layers means more, darker smoke."""
    def mean_lum(params):
        surf = _render_nebula_surface(variant[:7] + (params,), 64)
        return (pygame.surfarray.array3d(surf).astype(np.float64) @ LUMA).mean()
    assert mean_lum({'layers': 6}) < mean_lum({'layers': 1})


def test_params_override_the_defaults(variant):
    base = pygame.image.tobytes(_render_nebula_surface(variant[:7], 48), 'RGBA')
    over = pygame.image.tobytes(_render_nebula_surface(variant[:7] + ({'opacity': 0.1},), 48), 'RGBA')
    assert base != over


def test_teal_marble_carries_its_tuned_look(variant):
    """teal-marble was tuned in lp-studio and carries its own settings, so a
    later change to the renderer's defaults cannot quietly change it."""
    assert len(variant) == 8
    params = variant[7]
    assert variant[0] == 100
    assert params['layers'] == 4 and params['accents'] == 3
    assert params['accent_seed'] == 349 and params['accent_ink'] == (14, 14, 10)
    # every scalar the renderer reads is pinned, not inherited
    inherited = {k for k in SMOKE_LAYER_PARAMS if k not in params and not k.startswith('layer_')}
    assert not inherited, f'teal-marble inherits {sorted(inherited)} from the defaults'


def test_disc_edge_is_masked(pixels):
    _rgb, alpha = pixels
    n = alpha.shape[0]
    assert alpha[0, 0] == 0 and alpha[0, n - 1] == 0
    assert alpha[n // 2, n // 2] == 255


def test_is_deterministic(variant):
    a = pygame.image.tobytes(_render_nebula_surface(variant, 48), 'RGBA')
    b = pygame.image.tobytes(_render_nebula_surface(variant, 48), 'RGBA')
    assert a == b


# --- the tuning controls ----------------------------------------------------

def _bytes(variant, params, size=48):
    return pygame.image.tobytes(_render_nebula_surface(variant[:7] + (params,), size), 'RGBA')


def test_untouched_controls_leave_the_render_byte_identical(variant):
    """A style saved before these controls existed must look exactly the same."""
    explicit = {'opacity_variation': 1.0, 'spread': 1.0, 'rotate': 0.0,
                'layer_opacity': (1.0,) * SMOKE_MAX_LAYERS, 'layer_amount': (1.0,) * SMOKE_MAX_LAYERS,
                'layer_stretch': (1.0,) * SMOKE_MAX_LAYERS, 'layer_angle': (0.0,) * SMOKE_MAX_LAYERS,
                'layer_soft': (0,) * SMOKE_MAX_LAYERS}
    assert _bytes(variant, explicit) == _bytes(variant, {})


def test_layer_opacity_zero_everywhere_matches_global_opacity_zero(variant):
    assert (_bytes(variant, {'layer_opacity': (0.0,) * SMOKE_MAX_LAYERS})
            == _bytes(variant, {'opacity': 0.0}))


@pytest.mark.parametrize('params', [
    {'layer_opacity': (0.2,) + (1.0,) * (SMOKE_MAX_LAYERS - 1)},
    {'layer_amount': (2.0,) + (1.0,) * (SMOKE_MAX_LAYERS - 1)},
    {'layer_stretch': (3.0,) + (1.0,) * (SMOKE_MAX_LAYERS - 1)},
    {'layer_angle': (45.0,) + (0.0,) * (SMOKE_MAX_LAYERS - 1)},
    {'layer_soft': (4,) + (0,) * (SMOKE_MAX_LAYERS - 1)},
    {'opacity_variation': 0.0}, {'spread': 0.0}, {'rotate': 30.0},
])
def test_every_control_changes_the_render(variant, params):
    assert _bytes(variant, params) != _bytes(variant, {})


def test_trimming_one_layer_does_not_reshuffle_the_others(variant):
    """Trims apply after the random draws, so reshaping layer 1 leaves the random
    direction/stretch/opacity of every later layer where it was. With layer 1
    hidden, reshaping it must change nothing at all."""
    rest = SMOKE_MAX_LAYERS - 1
    hidden = {'layer_opacity': (0.0,) + (1.0,) * rest}
    reshaped = dict(hidden, layer_stretch=(3.0,) + (1.0,) * rest, layer_angle=(40.0,) + (0.0,) * rest,
                    layer_amount=(2.0,) + (1.0,) * rest, layer_soft=(5,) + (0,) * rest)
    assert _bytes(variant, reshaped) == _bytes(variant, hidden)


def test_short_trim_tuples_leave_later_layers_untouched(variant):
    assert _bytes(variant, {'layer_opacity': (1.0,)}) == _bytes(variant, {})


# --- dark accents -------------------------------------------------------------

ACCENTS = {'accents': 3, 'accent_amount': 0.15, 'accent_soft': 2}


def _rgb(variant, params, size=48):
    surf = _render_nebula_surface(variant[:7] + (params,), size)
    return pygame.surfarray.array3d(surf).astype(np.int32)


def test_accents_off_is_byte_identical(variant):
    """accents=0 must skip the pass entirely, so a look tuned without them
    renders exactly as it did before they existed, whatever else is set."""
    off = dict(ACCENTS, accents=0, accent_follow=0.0, accent_ink=(255, 0, 0))
    assert _bytes(variant, off) == _bytes(variant, {})


def test_accents_only_darken(variant):
    base, dark = _rgb(variant, {}), _rgb(variant, ACCENTS)
    lum = np.array([299, 587, 114])
    assert ((dark @ lum) <= (base @ lum) + 1000).all()
    assert (dark @ lum).mean() < (base @ lum).mean()


def test_accent_seed_changes_only_the_accents(variant):
    a = _bytes(variant, dict(ACCENTS, accent_seed=1))
    b = _bytes(variant, dict(ACCENTS, accent_seed=2))
    assert a != b


def test_full_follow_keeps_accents_out_of_clear_plastic(variant):
    """With follow=1, pixels the main smoke never touched stay exactly as they were."""
    params = {'layers': 1, 'amount': 0.05}
    base = _rgb(variant, params)
    dark = _rgb(variant, {**params, **ACCENTS, 'accent_follow': 1.0, 'accent_amount': 0.5})
    assert (dark != base).any()
    # the brightest body pixels carry no smoke, so follow=1 leaves them alone
    lum = base @ np.array([299, 587, 114])
    clear = lum >= np.percentile(lum, 99)
    assert np.abs(dark[clear] - base[clear]).max() <= 1


# --- field cache ----------------------------------------------------------------

from lpcore.vinyl import fractals  # noqa: E402


@pytest.fixture
def field_cache():
    fractals.enable_field_cache()
    yield
    fractals.disable_field_cache()


def test_kiosk_rendering_never_turns_the_field_cache_on(variant):
    """Only lp-studio's render worker enables the cache. Rendering a record the
    way the kiosk does must leave it off, so the kiosk never holds full-size
    fields in memory."""
    fractals.disable_field_cache()
    r = VinylRenderer(VinylSettings(style=f'nebula-{NAME}', label='art'))
    r.build_record(48, [0.0, 60.0, 130.0], 200.0, None, '/lp-test/album', 'A', 'B')
    assert fractals._FIELD_CACHE is None


def test_cached_render_is_byte_identical(variant, field_cache):
    params = dict(ACCENTS, layers=4)
    fractals.disable_field_cache()
    uncached = _bytes(variant, params)
    fractals.enable_field_cache()
    first = _bytes(variant, params)            # fills the cache
    second = _bytes(variant, params)           # served from it
    assert uncached == first == second


def test_colour_change_reuses_every_field(variant, field_cache, monkeypatch):
    _bytes(variant, dict(ACCENTS, layers=4))
    computed = []
    real = fractals._marble_blend_compute
    monkeypatch.setattr(fractals, '_marble_blend_compute',
                        lambda *a: computed.append(a) or real(*a))
    _bytes(variant, dict(ACCENTS, layers=4, ink=(0, 0, 0), opacity=0.2, amount=0.3,
                         accent_opacity=0.5, accent_follow=0.1))
    assert computed == []


def test_new_seed_does_not_reuse_fields(variant, field_cache):
    def render(seed):
        surf = _render_nebula_surface((seed,) + variant[1:7] + ({'layers': 2},), 48)
        return pygame.image.tobytes(surf, 'RGBA')
    assert render(101) != render(202)


def test_cache_stays_under_its_byte_limit(variant):
    fractals.enable_field_cache(max_bytes=3 * 96 * 96 * 8)   # three 48-radius fields
    try:
        for seed in range(6):
            _render_nebula_surface((seed,) + variant[1:7] + ({'layers': 2},), 48)
        assert fractals._FIELD_CACHE_BYTES <= 3 * 96 * 96 * 8
        assert len(fractals._FIELD_CACHE) <= 3
    finally:
        fractals.disable_field_cache()


# --- smoke shadow -----------------------------------------------------------------

def test_shadow_off_is_byte_identical(variant):
    assert _bytes(variant, {'shadow': 0.0, 'shadow_soft': 30}) == _bytes(variant, {})


def test_shadow_darkens_the_clear_plastic_beside_the_smoke(variant):
    base, shaded = _rgb(variant, {}), _rgb(variant, {'shadow': 0.8})
    lum = np.array([299, 587, 114])
    assert ((shaded @ lum) <= (base @ lum) + 1000).all()
    assert (shaded @ lum).mean() < (base @ lum).mean()


def test_shadow_softness_changes_the_shadow(variant):
    assert _bytes(variant, {'shadow': 0.8, 'shadow_soft': 2}) != _bytes(variant, {'shadow': 0.8, 'shadow_soft': 20})
