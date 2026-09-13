"""Tests for lp-studio's smoke family: the live controls for the layered-smoke
renderer that teal-marble ships with.

The point: studio is where the look gets tuned, and "Snippet" is how a tuned
look reaches the kiosk. So the chain has to hold end to end. Every control needs
a default, the defaults have to reproduce the shipped renderer exactly (so a
fresh smoke style starts as teal-marble), the style has to route to the right
renderer, and the snippet has to be valid Python you can paste.

    .venv/bin/python -m pytest tests/test_studio_smoke.py
"""
import ast
import os
import sys

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip('PySide6', reason='lp-studio needs PySide6 (requirements-deck.txt)')

import pygame

from lpcore.vinyl.fractals import SMOKE_LAYER_PARAMS, SMOKE_MAX_LAYERS
from lpstudio import studio


def _smoke_controls():
    return [c for g in studio.param_spec('smoke', advanced=True) for c in g['controls']
            if c['key'].startswith('smk_')]


def test_smoke_is_a_family():
    assert 'smoke' in studio.FAMILIES


def test_every_smoke_control_has_a_default():
    missing = [c['key'] for c in _smoke_controls() if c['key'] not in studio.DEFAULTS]
    assert not missing


def test_integer_controls_are_stored_as_integers():
    """setParam rounds only keys in _INTEGER_KEYS; a slider marked integer that
    is not listed would hand the renderer floats for layer counts and octaves."""
    wrong = [c['key'] for c in _smoke_controls() if c.get('integer') and c['key'] not in studio._INTEGER_KEYS]
    assert not wrong


def test_defaults_reproduce_the_shipped_renderer_defaults():
    assert studio._smoke_params(studio.DEFAULTS) == SMOKE_LAYER_PARAMS


def test_style_routes_to_the_layered_renderer():
    style = studio.build_style(dict(studio.DEFAULTS), 'smoke', False)
    assert style['type'] == 'nebula'
    assert style['variant'][6] == 'layers'
    assert style['variant'][7] == SMOKE_LAYER_PARAMS


def test_stretch_sliders_in_either_order_give_a_valid_range():
    p = dict(studio.DEFAULTS, smk_stretch_lo=5.0, smk_stretch_hi=2.0)
    assert studio._smoke_params(p)['stretch'] == (2.0, 5.0)


def test_render_vinyl_renders_a_smoke_disc():
    pygame.init()
    body, grooves, blend, shine = studio.render_vinyl(dict(studio.DEFAULTS), 'smoke', False, 40)
    assert body.get_size() == grooves.get_size() == shine.get_size() == (80, 80)
    assert blend == 'add'


def test_snippet_is_pasteable_python():
    c = studio.StudioController()
    c.setFamily('smoke')
    c.setName('teal-marble')
    snippet = c.catalogSnippet()
    entry = snippet.split("keep the name 'teal-marble':\n", 1)[1].split('\n\n', 1)[0].strip()
    assert entry.endswith(',')
    value = ast.literal_eval(entry[:-1])
    assert value[2] == 'teal-marble'
    assert value[6] == 'layers'
    assert value[7] == SMOKE_LAYER_PARAMS


def test_randomize_changes_only_the_composition():
    c = studio.StudioController()
    c.setFamily('smoke')
    before = dict(c._params)
    for _ in range(5):
        c.randomize()
        if c._params['smk_seed'] != before['smk_seed']:
            break
    changed = {k for k in c._params if c._params[k] != before[k]}
    assert changed == {'smk_seed'}


def test_hq_switch_notifies():
    c = studio.StudioController()
    seen = []
    c.hqChanged.connect(lambda: seen.append(c.getHq()))
    c.setHq(True)
    c.setHq(True)
    c.setHq(False)
    assert seen == [True, False]


def test_advanced_reveals_every_layer():
    simple = {g['group'] for g in studio.param_spec('smoke', advanced=False)}
    advanced = {g['group'] for g in studio.param_spec('smoke', advanced=True)}
    layers = {f'Layer {n}' for n in range(1, SMOKE_MAX_LAYERS + 1)}
    assert not (simple & layers)
    assert layers <= advanced


def test_a_layer_trim_reaches_the_renderer_on_the_right_layer():
    p = dict(studio.DEFAULTS, smk_l3_opacity=0.25, smk_l3_soft=4)
    params = studio._smoke_params(p)
    assert params['layer_opacity'][2] == 0.25 and params['layer_opacity'][1] == 1.0
    assert params['layer_soft'][2] == 4 and isinstance(params['layer_soft'][2], int)


def test_a_template_saved_before_these_controls_loads_unchanged(tmp_path, monkeypatch):
    """Old templates lack the new keys; they must fill in with the no-change
    defaults so the saved look renders identically."""
    import json
    monkeypatch.setattr(studio, 'TEMPLATE_DIR', str(tmp_path))
    old_keys = {k: v for k, v in studio.DEFAULTS.items()
                if not (k.startswith('smk_l') or k in ('smk_op_var', 'smk_spread', 'smk_rotate'))}
    (tmp_path / 'smoke').mkdir()
    (tmp_path / 'smoke' / 'old.json').write_text(json.dumps(
        {'name': 'old', 'family': 'smoke', 'advanced': False, 'params': old_keys}))
    c = studio.StudioController()
    c.loadTemplate('smoke/old')
    assert studio._smoke_params(c._params) == SMOKE_LAYER_PARAMS


def test_dark_accents_are_always_visible_and_reach_the_renderer():
    groups = {g['group'] for g in studio.param_spec('smoke', advanced=False)}
    assert {'Dark accents', 'Accent ink'} <= groups
    params = studio._smoke_params(dict(studio.DEFAULTS, smk_acc_count=3, smk_acc_stretch_lo=6.0,
                                       smk_acc_stretch_hi=2.0))
    assert params['accents'] == 3 and isinstance(params['accents'], int)
    assert params['accent_stretch'] == (2.0, 6.0)


def test_smoke_shadow_controls_reach_the_renderer():
    params = studio._smoke_params(dict(studio.DEFAULTS, smk_shadow=0.4, smk_shadow_soft=9))
    assert params['shadow'] == 0.4
    assert params['shadow_soft'] == 9 and isinstance(params['shadow_soft'], int)


@pytest.mark.parametrize('family', studio.FAMILIES)
def test_every_family_offers_vinyl_effects(family):
    groups = {g['group']: g for g in studio.param_spec(family)}
    assert [c['label'] for c in groups['Vinyl Effects']['controls']] == [
        'Glass', 'Deep edge', 'Rim light', 'Grooves']


def test_effect_toggles_reach_the_preview():
    p = dict(studio.DEFAULTS, fx_glass=1, fx_rim_light=1)
    assert studio.effects_from(p) == ['glass', 'rim-light']
    assert studio.effects_from(studio.DEFAULTS) == []


@pytest.mark.parametrize('family', studio.FAMILIES)
def test_preview_grooves_are_what_the_kiosk_draws(family):
    """The studio used to draw grooves from its own sliders, which nothing in
    lp or lp-deck read, so a design could look different once shipped. Its
    grooves must now be exactly the renderer's, for every family."""
    from lpcore.vinyl.render import VinylRenderer
    from lpcore.vinyl.settings import VinylSettings
    pygame.init()
    p = dict(studio.DEFAULTS)
    _body, grooves, blend, _shine = studio.render_vinyl(p, family, False, 30)
    try:
        style = studio.build_style(p, family, False)
        want, want_blend = VinylRenderer(VinylSettings()).build_grooves_overlay(
            30, style, studio._STUDIO_BOUNDARIES, studio._STUDIO_ALBUM_DUR)
    finally:
        studio._clear_live()
    assert blend == want_blend
    assert pygame.image.tobytes(grooves, 'RGBA') == pygame.image.tobytes(want, 'RGBA')


def test_no_groove_sliders_left_to_mislead():
    for family in studio.FAMILIES:
        groups = {g['group'] for g in studio.param_spec(family, advanced=True)}
        assert 'Grooves' not in groups
    assert not [k for k in studio.DEFAULTS if k.startswith('grv_')]



def test_grooves_choice_reaches_the_preview():
    pygame.init()
    smooth = list(studio.catalog.GROOVE_TREATMENTS).index('smooth')
    assert studio.grooves_from(studio.DEFAULTS) == 'auto'
    p = dict(studio.DEFAULTS, fx_grooves=smooth)
    assert studio.grooves_from(p) == 'smooth'
    _body, grooves, _blend, _shine = studio.render_vinyl(p, 'smoke', False, 30)
    assert pygame.surfarray.array_alpha(grooves).max() == 0
