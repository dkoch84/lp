"""Tests for lpcore.vinyl.ramp: the brightness ramp a smoke vinyl needs.

purple-marble and pink-marble were first tuned with smoke colours that did not
step down in brightness. They looked fine in lp-studio's small preview and
rendered flat on the kiosk. The fix was teal-marble's ratios (mid ~72%, ink ~25%,
accent ~9% of the light colour's luma). These pin both sides: the colours that
looked right pass, the ones that rendered flat are flagged, and every marble in
the catalog passes.

    .venv/bin/python -m pytest tests/test_ramp.py
"""
import os
import sys

import numpy as np
import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.vinyl import ramp
from lpcore.vinyl.fractals import NEBULA_VARIANTS, _render_nebula_surface

# (light, mid, ink, accent_ink)
TEAL = ((68, 150, 140), (48, 112, 104), (16, 40, 34), (14, 14, 10))
PURPLE = ((120, 105, 225), (85, 70, 170), (28, 20, 70), (10, 8, 20))
PINK = ((210, 140, 155), (170, 95, 115), (80, 25, 40), (35, 5, 15))
# As first tuned: flat on the big screen.
PURPLE_FIRST = ((61, 56, 167), (72, 53, 189), (75, 51, 198), (218, 195, 190))
PINK_FIRST = ((215, 172, 165), (232, 182, 182), (255, 132, 135), (255, 0, 15))


@pytest.fixture(scope='module', autouse=True)
def _pygame():
    pygame.init()


def _hue_gap(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


# --- check_ramp ---------------------------------------------------------------

@pytest.mark.parametrize('colours', [TEAL, PURPLE, PINK], ids=['teal', 'purple', 'pink'])
def test_colours_that_looked_right_pass(colours):
    assert ramp.check_ramp(*colours) == []


@pytest.mark.parametrize('colours', [PURPLE_FIRST, PINK_FIRST], ids=['purple-first', 'pink-first'])
def test_colours_that_rendered_flat_are_flagged(colours):
    issues = ramp.check_ramp(*colours)
    assert any(i.level == 'bad' and i.keys == ('ink',) for i in issues)
    assert any(i.keys == ('mid',) for i in issues)


def test_light_accents_are_flagged():
    issues = ramp.check_ramp(*PURPLE_FIRST)
    assert any(i.keys == ('accent_ink',) for i in issues)


def test_a_light_colour_with_no_room_below_is_flagged():
    light = (40, 30, 60)
    d = ramp.derive_ramp(light)
    issues = ramp.check_ramp(light, d['mid'], d['ink'], d['accent_ink'])
    assert [i.keys for i in issues] == [('light',)]


def test_every_smoke_style_in_the_catalog_passes():
    smoke = [v for v in NEBULA_VARIANTS if len(v) > 7 and v[6] == 'layers']
    assert len(smoke) >= 15
    for v in smoke:
        p = v[7]
        assert ramp.check_ramp(p['light'], p['mid'], p['ink'], p['accent_ink']) == [], v[2]


def test_issue_messages_say_what_to_aim_for():
    ink = next(i for i in ramp.check_ramp(*PINK_FIRST) if i.keys == ('ink',))
    assert 'Aim for about 46' in ink.message
    assert ink.as_dict() == {'level': 'bad', 'keys': ['ink'], 'message': ink.message}


# --- building a ramp ----------------------------------------------------------

@pytest.mark.parametrize('target', [10, 32, 92, 124, 163, 200])
@pytest.mark.parametrize('hue', [0, 48, 173, 218, 300])
def test_at_luma_hits_the_target(hue, target):
    assert abs(ramp.luma(ramp.at_luma(hue, 0.6, target)) - target) <= 1.0


def test_at_luma_gives_up_saturation_to_keep_brightness():
    colour = ramp.at_luma(240, 1.0, 200)      # pure blue can't be this bright
    assert abs(ramp.luma(colour) - 200) <= 1.0
    assert ramp.hue_sat(colour)[1] < 0.9


@pytest.mark.parametrize('light', [TEAL[0], PURPLE[0], PINK[0], (127, 131, 135)],
                         ids=['teal', 'purple', 'pink', 'grey'])
def test_derived_ramp_steps_down_in_the_light_colours_hue(light):
    d = ramp.derive_ramp(light)
    lum = ramp.luma(light)
    for key, share in ramp.RAMP.items():
        assert abs(ramp.luma(d[key]) - share * lum) <= 1.5, key
    hue, sat = ramp.hue_sat(light)
    if sat > 0.2:
        assert _hue_gap(ramp.hue_sat(d['mid'])[0], hue) < 6
        assert _hue_gap(ramp.hue_sat(d['ink'])[0], hue) < 10
    assert ramp.check_ramp(light, d['mid'], d['ink'], d['accent_ink']) == []


def test_matches_ramp():
    d = ramp.derive_ramp(PURPLE[0])
    assert ramp.matches_ramp(PURPLE[0], d['mid'], d['ink'], d['accent_ink'])
    assert not ramp.matches_ramp(*PURPLE_FIRST)


# --- contrast of a render -----------------------------------------------------

def _variant(colours, name='teal-marble'):
    base = next(v for v in NEBULA_VARIANTS if v[2] == name)
    light, mid, ink, accent = colours
    return base[:7] + ({**base[7], 'light': light, 'mid': mid, 'ink': ink, 'accent_ink': accent},)


def _stats(colours):
    surf = _render_nebula_surface(_variant(colours), 80)
    w, h = surf.get_size()
    return ramp.contrast(pygame.image.tobytes(surf, 'RGBA'), w, h)


def test_a_flat_render_warns():
    stats = _stats(PURPLE_FIRST)
    assert stats['iqr'] < ramp.IQR_MIN
    assert [i.keys for i in ramp.check_contrast(stats)] == [('contrast',)]


@pytest.mark.parametrize('colours', [TEAL, PURPLE, PINK], ids=['teal', 'purple', 'pink'])
def test_a_render_with_a_ramp_does_not(colours):
    stats = _stats(colours)
    assert stats['iqr'] >= ramp.IQR_MIN
    assert ramp.check_contrast(stats) == []


def test_contrast_ignores_the_label_and_the_transparent_corners():
    n = 64
    img = np.zeros((n, n, 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(xx + 0.5 - n / 2, yy + 0.5 - n / 2) / (n / 2)
    img[r <= 1.0] = (100, 100, 100, 255)
    img[r < 0.3] = (255, 255, 255, 255)        # a white label
    stats = ramp.contrast(img.tobytes(), n, n, inner=0.35)
    assert stats['p2'] == pytest.approx(100) and stats['p98'] == pytest.approx(100)


def test_contrast_of_nothing_opaque_is_none():
    assert ramp.contrast(bytes(16 * 16 * 4), 16, 16) is None
    assert ramp.check_contrast(None) == []
