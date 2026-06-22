"""Smoke + regression tests for the lpcore.vinyl renderer.

The point: render *every style and every label type*, so a crash in a code path
(e.g. fractal labels) can't hide behind a single happy-path check — that exact
gap let a `key in None` crash ship. Headless (dummy SDL); fast (small surfaces).

Run standalone (no pytest needed):
    .venv/bin/python tests/test_render.py
or under pytest if installed:
    .venv/bin/python -m pytest tests/
"""
import hashlib
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
pygame.init()
pygame.font.init()

from lpcore.vinyl.render import VinylRenderer
from lpcore.vinyl.settings import VinylSettings
from lpcore.vinyl.catalog import (VINYL_COLORS, MANDELBROT_VARIANTS, MUNAFO_VARIANTS,
                                  LABEL_COLORS, LABEL_TEXT_MODES, DECOR_EMOJI)
from lpcore.vinyl.fractals import NEBULA_VARIANTS

ALBUM = '/tmp/lp-test-album'        # missing art is fine — exercises the fallback
BOUNDS = [0.0, 50.0, 120.0, 190.0]
DUR = 260.0
SIZE = 96                           # int, as real callers pass (record_size * SS)

_M = MANDELBROT_VARIANTS
_MAND = ['mandelbrot-%s-%s' % (v[4], v[5]) for v in _M]
_NEB = ['nebula-' + v[2] for v in NEBULA_VARIANTS]
_MUN = ['munafo-' + v[0] for v in MUNAFO_VARIANTS]


def _render(style, label, **settings_kw):
    r = VinylRenderer(VinylSettings(style=style, label=label, **settings_kw))
    st = r.get_vinyl_style(ALBUM)
    body = r.build_record(SIZE, BOUNDS, DUR, None, ALBUM, 'ARTIST', 'ALBUM')
    grv, blend = r.build_grooves_overlay(SIZE, st, BOUNDS, DUR)
    shine = r.build_shine_overlay(SIZE, st)
    assert body is not None and grv is not None and shine is not None
    assert body.get_size() == (SIZE * 2, SIZE * 2)
    return body


def test_every_style_renders():
    # a representative sweep of every body code path (fractal families share code,
    # so a few of each exercises the path without rendering all 84 mandelbrots)
    styles = (['random', 'black', 'clear', 'picture']
              + ['color-' + c for c in VINYL_COLORS]
              + _MAND[:3] + _NEB[:3] + _MUN
              + ['pattern', 'pattern-mandelbrot', 'pattern-nebula', 'pattern-munafo'])
    for style in styles:
        _render(style, 'art')


def test_every_label_type_renders():
    # the path that regressed: colour / legacy / fractal / julia labels on a vinyl
    labels = (['art', 'color-' + next(iter(VINYL_COLORS)),
               'label-' + next(iter(LABEL_COLORS)),
               _MAND[0], _NEB[0], _MUN[0], 'julia-dendrite'])
    for label in labels:
        _render('color-cyan', label)


def test_label_text_modes_and_decor():
    for mode in LABEL_TEXT_MODES:
        _render('color-cyan', 'art', label_text=mode,
                decor1=next(iter(DECOR_EMOJI)), decor1_color='#ff0000')


def test_brightness_levels():
    for b in (0, 50, 100):
        _render('color-cyan', 'art', brightness=b)


def test_render_is_deterministic():
    def h(style):
        surf = _render(style, 'art')
        return hashlib.sha256(bytes(surf.get_view('1'))).hexdigest()
    for style in ['black', 'color-cyan', _MAND[0], _NEB[0]]:
        assert h(style) == h(style), style   # same inputs → identical pixels


def test_vinyl_settings_validation():
    s = VinylSettings()
    s.update(brightness=50, label_text='blocky', artist_color='#abcdef', decor1='owl')
    assert s.brightness == 50 and s.label_text == 'blocky' and s.decor1 == 'owl'
    bad = [dict(brightness=200), dict(brightness=-1), dict(brightness='x'),
           dict(label_text='spin'), dict(label_font='comic'),
           dict(artist_color='red'), dict(decor1='dragon')]
    for kw in bad:
        try:
            VinylSettings().update(**kw)
        except ValueError:
            continue
        raise AssertionError(f"VinylSettings accepted invalid {kw}")


if __name__ == '__main__':
    import traceback
    tests = [v for k, v in sorted(globals().items())
             if k.startswith('test_') and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
