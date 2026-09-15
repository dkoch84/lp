"""Tests for styles kept as data files (lpcore.vinyl.styles).

lp-studio ships a style by writing lpcore/vinyl/styles/nebula/<name>.json, and
fractals.py loads those into NEBULA_VARIANTS. What must hold: the files turn
into exactly the tuples that were hand-written before, in the same place in the
catalog (an album without a chosen style picks one by position), their cached
images stay current, and a broken file fails loudly instead of quietly dropping
a style.

    .venv/bin/python -m pytest tests/test_styles_data.py
"""
import json
import os
import sys

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.vinyl import fractals, prerender, styles
from lpcore.vinyl.cache import NEBULA_CACHE_DIR


def _entry(name='test-marble', order=1, family='smoke', **params):
    return {'name': name, 'family': family, 'order': order, 'seed': 7,
            'params': params or {'layers': 2, 'stretch': (2.0, 2.4), 'light': (68, 150, 140)},
            'studio': {'ramp_linked': True}}


# --- the file format ----------------------------------------------------------

def test_round_trip(tmp_path):
    entry = _entry()
    styles.write(entry, root=str(tmp_path))
    [back] = styles.load(root=str(tmp_path))
    assert styles.to_tuples(back['params']) == entry['params']
    assert back['studio'] == {'ramp_linked': True}


def test_write_leaves_no_partial_file(tmp_path):
    styles.write(_entry(), root=str(tmp_path))
    assert sorted(os.listdir(tmp_path / 'nebula')) == ['test-marble.json']


def test_colours_stay_on_one_line(tmp_path):
    text = open(styles.write(_entry(), root=str(tmp_path))).read()
    assert '"light": [68, 150, 140]' in text
    assert json.loads(text)['params']['stretch'] == [2.0, 2.4]


def test_sorted_by_order_then_name(tmp_path):
    for name, order in (('b-marble', 2), ('c-marble', 1), ('a-marble', 2)):
        styles.write(_entry(name, order), root=str(tmp_path))
    assert styles.names(root=str(tmp_path)) == ['c-marble', 'a-marble', 'b-marble']
    assert styles.next_order(root=str(tmp_path)) == 3


@pytest.mark.parametrize('bad', ['Teal Marble', 'teal_marble', '-teal', '', 'teal--marble'])
def test_bad_names_are_refused(tmp_path, bad):
    assert not styles.valid_name(bad)
    with pytest.raises(styles.StyleFileError):
        styles.write(_entry(bad), root=str(tmp_path))


def test_a_broken_file_fails_loudly(tmp_path):
    folder = tmp_path / 'nebula'
    folder.mkdir()
    (folder / 'x-marble.json').write_text('{"name": "x-marble", "family": "smoke"}')
    with pytest.raises(styles.StyleFileError, match='missing order, seed, params'):
        styles.load(root=str(tmp_path))
    (folder / 'x-marble.json').write_text(json.dumps(_entry('y-marble')))
    with pytest.raises(styles.StyleFileError, match='does not match the file name'):
        styles.load(root=str(tmp_path))
    (folder / 'x-marble.json').write_text(json.dumps(_entry('x-marble', family='plaid')))
    with pytest.raises(styles.StyleFileError, match='unknown family'):
        styles.load(root=str(tmp_path))


# --- the shipped styles in the catalog ----------------------------------------

def test_shipped_styles_sit_together_after_marble_in_order():
    names = [v[2] for v in fractals.NEBULA_VARIANTS]
    shipped = styles.names()
    assert {'teal-marble', 'purple-marble', 'pink-marble'} <= set(shipped)
    start = names.index('marble') + 1
    assert names[start:start + len(shipped)] == shipped
    assert names[start + len(shipped)] == 'galaxy'
    assert len(set(names)) == len(names), 'a style name is listed twice'


def test_shipped_smoke_styles_are_layers_variants_with_tuples():
    by_name = {v[2]: v for v in fractals.NEBULA_VARIANTS}
    for entry in styles.load():
        v = by_name[entry['name']]
        assert v[:2] == (entry['seed'], None) and v[3:7] == (1.0, 5, 6, 'layers')
        assert isinstance(v[7]['stretch'], tuple) and isinstance(v[7]['light'], tuple)


def test_cached_images_are_current_for_shipped_styles():
    keys = prerender.load_keys(NEBULA_CACHE_DIR)
    for v in fractals.NEBULA_VARIANTS:
        if v[2] in styles.names():
            assert keys.get(v[2]) == prerender.style_key(fractals._render_nebula_surface, v), v[2]


def test_clouds_and_nebula_files_build_palettes(tmp_path, monkeypatch):
    root = str(tmp_path)
    styles.write(_entry('pale-clouds', 1, 'clouds', cloud=(250, 220, 230), sky=(160, 200, 240),
                        saturation=1.2), root=root)
    styles.write(_entry('two-tone', 2, 'nebula', col1=(40, 10, 120), col2=(200, 80, 5),
                        amp1=(200, 60, 135), amp2=(55, 140, 40), mods1=('t1', 'hs', 'sin'),
                        mods2=('t3', 't1', 'inv_t3'), sin_freq=8.0, bright='std', sparkle='none',
                        saturation=1.5, warp=6, arm=7), root=root)
    monkeypatch.setattr(styles, 'STYLES_DIR', root)
    clouds, nebula = fractals._variants_from_files()
    assert clouds[2:] == ('pale-clouds', 1.2, 6, 7, 'clouds') and callable(clouds[1])
    assert nebula[2:] == ('two-tone', 1.5, 6, 7) and callable(nebula[1])
    pygame.init()
    for v in (clouds, nebula):
        assert fractals._render_nebula_surface(v, 12).get_size() == (24, 24)
