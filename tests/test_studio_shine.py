"""Tests that lp-studio's shine is the one that ships.

The studio used to offer Shine sliders, but lp and lp-deck draw the same shine
for every style and nothing saved from the studio carried those settings over,
so the sliders tuned a preview nobody would see. Now the preview draws the
production shine, and designs saved with the old keys still load.

    .venv/bin/python -m pytest tests/test_studio_shine.py
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

from lpstudio import studio

FAMILIES = ('mandelbrot', 'color', 'nebula', 'clouds', 'smoke', 'black', 'clear')


@pytest.mark.parametrize('family', FAMILIES)
def test_no_shine_controls(family):
    for advanced in (False, True):
        groups = studio.param_spec(family, advanced)
        assert 'Shine' not in [g['group'] for g in groups]
        keys = [c['key'] for g in groups for c in g['controls']]
        assert not [k for k in keys if k.startswith('shine_')]
    assert not [k for k in studio.DEFAULTS if k.startswith('shine_')]


@pytest.mark.parametrize('family', ('smoke', 'color', 'black'))
def test_preview_shine_is_the_production_shine(family):
    p = dict(studio.DEFAULTS)
    _body, _grooves, _blend, shine = studio.render_vinyl(p, family, False, 40)
    try:
        style = studio.build_style(p, family, False)
        expected = studio.VinylRenderer(studio.VinylSettings()).build_shine_overlay(40, style)
    finally:
        studio._clear_live()
    assert pygame.image.tobytes(shine, 'RGBA') == pygame.image.tobytes(expected, 'RGBA')


def test_designs_saved_with_shine_settings_still_load(monkeypatch, tmp_path):
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.instance() or QGuiApplication([])
    monkeypatch.setattr(studio, 'TEMPLATE_DIR', str(tmp_path))
    (tmp_path / 'smoke').mkdir()
    (tmp_path / 'smoke' / 'old.json').write_text(json.dumps({
        'name': 'old', 'family': 'smoke', 'advanced': False,
        'params': {'smk_seed': 349, 'shine_gloss': 0.2, 'shine_angle': -30.0}}))
    controller = studio.StudioController()
    controller.loadTemplate('smoke/old')
    params = controller._params
    assert params['smk_seed'] == 349
    assert not [k for k in params if k.startswith('shine_')]
