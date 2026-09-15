"""Tests for lp-studio's guardrails, undo history and shipping.

purple-marble and pink-marble left the studio with smoke colours that did not
step down in brightness, and only looked wrong on the kiosk. So the studio now
links the darker colours to the light one (lpcore.vinyl.ramp) and warns about a
flat ramp or a flat render. Tuning is exploratory, so every change can be undone,
and a finished style ships as a style file that renders exactly like the preview.

    .venv/bin/python -m pytest tests/test_studio_guardrails.py
"""
import json
import os
import sys

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip('PySide6', reason='lp-studio needs PySide6 (requirements-deck.txt)')

import pygame

from lpcore.vinyl import fractals, ramp, styles
from lpcore.vinyl.fractals import SMOKE_LAYER_PARAMS
from lpstudio import studio

RAMP_PREFIXES = ('smk_light', 'smk_mid', 'smk_ink', 'smk_acc_ink')
# purple-marble as first tuned: flat on the big screen
PURPLE_FIRST = ((61, 56, 167), (72, 53, 189), (75, 51, 198), (218, 195, 190))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def smoke(clock):
    c = studio.StudioController(clock=clock)
    c.setFamily('smoke')
    clock.t += 10
    return c


@pytest.fixture
def shipper(tmp_path, clock):
    c = studio.StudioController(clock=clock)
    c.styles_root = str(tmp_path)
    launched = []
    c.launch_prerender = launched.append
    return c, launched


def _colours(c):
    return studio.ramp_colours(c._params)


def _render(variant):
    pygame.init()
    return pygame.image.tobytes(fractals._render_nebula_surface(variant, 40), 'RGBA')


# --- the linked colour ramp ---------------------------------------------------

def test_darker_colours_follow_the_light_colour_while_linked(smoke):
    assert smoke.rampLinked
    smoke.setColor('smk_light', '#7869e1')
    got = _colours(smoke)
    assert got['light'] == (120, 105, 225)
    want = ramp.derive_ramp((120, 105, 225))
    assert {k: got[k] for k in want} == want


def test_one_channel_of_the_light_colour_moves_the_ramp_too(smoke):
    smoke.setParam('smk_light_g', 60)
    got = _colours(smoke)
    assert got['ink'] == ramp.derive_ramp(got['light'])['ink']


def test_editing_a_darker_colour_unlinks_and_keeps_it(smoke):
    smoke.setParam('smk_ink_r', 5)
    assert not smoke.rampLinked and smoke.param('smk_ink_r') == 5
    before = _colours(smoke)['ink']
    smoke.setParam('smk_light_r', 200)
    assert _colours(smoke)['ink'] == before


def test_linking_fixes_a_flat_ramp(smoke):
    smoke.setRampLinked(False)
    for prefix, rgb in zip(RAMP_PREFIXES, PURPLE_FIRST):
        smoke.setColor(prefix, studio._hex(rgb))
    flagged = {k for g in smoke.guardrails for k in g['keys']}
    assert {'mid', 'ink', 'accent_ink'} <= flagged
    smoke.setRampLinked(True)
    assert smoke.guardrails == []
    assert _colours(smoke)['light'] == PURPLE_FIRST[0]


def test_a_flat_render_adds_a_contrast_warning(smoke):
    smoke.setContrast({'p2': 69, 'p25': 71, 'p75': 73, 'p98': 123, 'iqr': 2})
    assert [g['keys'] for g in smoke.guardrails] == [['contrast']]
    smoke.setContrast({'p2': 54, 'p25': 87, 'p75': 112, 'p98': 124, 'iqr': 25})
    assert smoke.guardrails == []


def test_guardrails_are_for_smoke_only(clock):
    c = studio.StudioController(clock=clock)
    c.setFamily('color')          # a solid colour is flat on purpose
    c.setContrast({'p2': 80, 'p25': 80, 'p75': 80, 'p98': 80, 'iqr': 0})
    assert c.guardrails == []


def test_ramp_swatches_show_brightness_against_the_target(smoke):
    swatches = {s['key']: s for s in smoke.rampSwatches}
    assert swatches['light']['color'] == '#44968c'
    assert swatches['light']['luma'] == 124
    assert (swatches['ink']['luma'], swatches['ink']['target']) == (32, 31)


def _write_template(tmp_path, monkeypatch, colours, **extra):
    monkeypatch.setattr(studio, 'TEMPLATE_DIR', str(tmp_path))
    params = {f'{prefix}_{c}': v
              for prefix, rgb in zip(RAMP_PREFIXES, colours) for c, v in zip('rgb', rgb)}
    (tmp_path / 'smoke').mkdir(exist_ok=True)
    (tmp_path / 'smoke' / 't.json').write_text(
        json.dumps({'name': 't', 'family': 'smoke', 'params': params, **extra}))


def test_an_old_template_with_its_own_colours_opens_unlinked(tmp_path, monkeypatch, clock):
    _write_template(tmp_path, monkeypatch, PURPLE_FIRST)
    c = studio.StudioController(clock=clock)
    c.loadTemplate('smoke/t')
    assert not c.rampLinked
    assert tuple(_colours(c).values()) == PURPLE_FIRST


def test_an_old_template_that_follows_the_ramp_opens_linked(tmp_path, monkeypatch, clock):
    light = (77, 123, 202)
    d = ramp.derive_ramp(light)
    _write_template(tmp_path, monkeypatch, (light, d['mid'], d['ink'], d['accent_ink']))
    c = studio.StudioController(clock=clock)
    c.loadTemplate('smoke/t')
    assert c.rampLinked


def test_a_saved_link_setting_is_kept(tmp_path, monkeypatch, clock):
    _write_template(tmp_path, monkeypatch, PURPLE_FIRST, ramp_linked=True)
    c = studio.StudioController(clock=clock)
    c.loadTemplate('smoke/t')
    assert c.rampLinked and tuple(_colours(c).values()) == PURPLE_FIRST


# --- undo / redo ----------------------------------------------------------------

def test_a_slider_drag_undoes_as_one_step(smoke, clock):
    for value in (0.2, 0.3, 0.4):
        smoke.setParam('smk_amount', value)
        clock.t += 0.1
    smoke.undo()
    assert smoke.param('smk_amount') == pytest.approx(SMOKE_LAYER_PARAMS['amount'])


def test_a_pause_starts_a_new_step(smoke, clock):
    smoke.setParam('smk_amount', 0.3)
    clock.t += 1
    smoke.setParam('smk_amount', 0.4)
    smoke.undo()
    assert smoke.param('smk_amount') == pytest.approx(0.3)


def test_separate_controls_undo_separately_and_redo(smoke):
    smoke.setParam('smk_amount', 0.3)
    smoke.setParam('smk_gamma', 3.0)
    smoke.undo()
    assert smoke.param('smk_gamma') == pytest.approx(SMOKE_LAYER_PARAMS['gamma'])
    assert smoke.param('smk_amount') == pytest.approx(0.3)
    assert smoke.canRedo
    smoke.redo()
    assert smoke.param('smk_gamma') == pytest.approx(3.0)


def test_a_new_change_after_undo_drops_redo(smoke):
    smoke.setParam('smk_amount', 0.3)
    smoke.undo()
    smoke.setParam('smk_gamma', 3.0)
    assert not smoke.canRedo


def test_undo_restores_colours_moved_by_the_ramp(smoke):
    before = _colours(smoke)
    smoke.setColor('smk_light', '#4d7bca')
    smoke.undo()
    assert _colours(smoke) == before and smoke.rampLinked


def test_undo_brings_back_the_family(smoke):
    smoke.undo()
    assert smoke.family == 'mandelbrot' and not smoke.canUndo


def test_dirty_follows_saves_and_undo(tmp_path, monkeypatch, smoke):
    monkeypatch.setattr(studio, 'TEMPLATE_DIR', str(tmp_path))
    smoke.setName('mine')
    smoke.save()
    assert not smoke.dirty
    smoke.setParam('smk_amount', 0.3)
    assert smoke.dirty
    smoke.undo()
    assert not smoke.dirty


def test_save_asks_before_replacing_a_template_that_was_not_loaded(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(studio, 'TEMPLATE_DIR', str(tmp_path))
    a = studio.StudioController(clock=clock)
    a.setFamily('smoke')
    a.setName('mine')
    assert not a.saveNeedsConfirm()
    a.save()
    assert not a.saveNeedsConfirm()          # saving over itself again is fine
    b = studio.StudioController(clock=clock)
    b.setFamily('smoke')
    b.setName('mine')
    assert b.saveNeedsConfirm()
    b.loadTemplate('smoke/mine')
    assert not b.saveNeedsConfirm()


def test_reset_leaves_other_families_alone(smoke):
    smoke.setParam('cld_seed', 5)
    smoke.setParam('smk_seed', 5)
    smoke.reset()
    assert smoke.param('smk_seed') == studio.DEFAULTS['smk_seed']
    assert smoke.param('cld_seed') == 5


# --- shipped styles -------------------------------------------------------------

@pytest.mark.parametrize('name', ['teal-marble', 'pink-marble', 'cobalt-marble'])
def test_a_shipped_style_loads_back_exactly(name, clock):
    c = studio.StudioController(clock=clock)
    c.loadShipped(name)
    assert (c.family, c.name) == ('smoke', name) and not c.dirty
    shipped = next(v for v in fractals.NEBULA_VARIANTS if v[2] == name)
    assert _render(studio.build_style(c._params, 'smoke', c.advanced)['variant']) == _render(shipped)


def test_layer_trims_and_link_state_come_back_with_a_shipped_style(clock):
    c = studio.StudioController(clock=clock)
    c.loadShipped('pink-marble')
    assert c.advanced and c.param('smk_l2_opacity') == pytest.approx(1.68)
    assert not c.rampLinked
    c.loadShipped('cobalt-marble')
    assert not c.advanced and c.rampLinked


def test_ship_writes_a_style_file_that_renders_like_the_preview(shipper, monkeypatch, tmp_path):
    c, launched = shipper
    c.setFamily('smoke')
    c.setColor('smk_light', '#4d7bca')
    c.setParam('smk_seed', 4242)
    path = c.ship('test-marble')
    assert path == str(tmp_path / 'nebula' / 'test-marble.json')
    assert launched == ['test-marble'] and c.shipping and c.name == 'test-marble'
    entry = json.load(open(path))
    assert entry['order'] == 1 and entry['studio']['ramp_linked'] is True
    monkeypatch.setattr(styles, 'STYLES_DIR', str(tmp_path))
    [variant] = fractals._variants_from_files()
    assert _render(variant) == _render(studio.build_style(c._params, 'smoke', False)['variant'])


def test_shipping_again_keeps_the_style_in_its_place(shipper, tmp_path):
    c, _ = shipper
    c.setFamily('smoke')
    for name in ('a-marble', 'b-marble', 'a-marble'):
        c.ship(name)
    assert styles.names(root=str(tmp_path)) == ['a-marble', 'b-marble']


def test_ship_refuses_what_it_cannot_ship(shipper):
    c, launched = shipper
    c.setFamily('smoke')
    assert c.ship('galaxy') == ''            # a style defined in fractals.py
    assert 'built-in' in c.status
    assert c.ship('Cobalt Marble') == ''
    c.setFamily('mandelbrot')
    assert c.ship('new-zoom') == ''
    assert launched == []


def test_ship_check_describes_the_name(shipper):
    c, _ = shipper
    c.setFamily('smoke')
    c.ship('mine-marble')
    assert c.shipCheck('galaxy')['builtin'] and not c.shipCheck('galaxy')['ok']
    check = c.shipCheck('mine-marble')
    assert check['ok'] and check['exists']
    assert not c.shipCheck('fresh-marble')['exists']


def test_the_render_result_reaches_the_status_line(shipper):
    c, _ = shipper
    c._set_shipping(True)
    c._prerender_finished('x-marble', 0, '')
    assert not c.shipping and c.status.startswith('x-marble is ready')
    c._prerender_finished('x-marble', 1, 'rendering...\nKeyError: nope\n')
    assert c.status == 'Rendering x-marble failed: KeyError: nope'


def test_clouds_and_nebula_ship_and_load_back(shipper, monkeypatch, tmp_path, clock):
    c, _ = shipper
    c.setFamily('clouds')
    c.setParam('cld_seed', 77)
    c.ship('pale-sky')
    c.setFamily('nebula')
    c.setAdvanced(True)
    c.setParam('neb_seed', 9)
    c.ship('two-tone')
    monkeypatch.setattr(styles, 'STYLES_DIR', str(tmp_path))
    for variant, family in zip(fractals._variants_from_files(), ('clouds', 'nebula')):
        d = studio.StudioController(clock=clock)
        d.styles_root = str(tmp_path)
        d.loadShipped(variant[2])
        assert d.family == family
        mine = studio.build_style(d._params, family, d.advanced)['variant']
        assert _render(mine) == _render(variant)
