"""Tests for `make prerender` (lpcore.vinyl.prerender).

A style with no cached image renders live every time it is drawn, which froze
lp-deck for tens of seconds on teal-marble. The tool renders only what's
missing, so it must: skip styles that already have an image, render a style
named with --only whether cached or not, refuse unknown names, and never leave
a half-written image where a running app could load it.

The real renders are replaced with a stub and the cache folders point at a temp
dir, so this is fast and never touches lpcore/cache.

    .venv/bin/python -m pytest tests/test_prerender.py
"""
import os
import sys

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.vinyl import prerender


@pytest.fixture
def cache(tmp_path, monkeypatch):
    pygame.init()
    mandel, nebula = tmp_path / "mandelbrot", tmp_path / "nebula"
    monkeypatch.setattr(prerender, "CACHE_DIR", str(mandel))
    monkeypatch.setattr(prerender, "NEBULA_CACHE_DIR", str(nebula))
    rendered = []

    def stub(variant, size):
        rendered.append(variant)
        return pygame.Surface((4, 4), pygame.SRCALPHA)

    monkeypatch.setattr(prerender, "_render_mandelbrot_surface", stub)
    monkeypatch.setattr(prerender, "_render_nebula_surface", stub)
    monkeypatch.setattr(prerender, "MANDELBROT_VARIANTS", [(0, 0, 1, 10, "zoom", "purple")])
    monkeypatch.setattr(prerender, "NEBULA_VARIANTS", [(1, None, "teal-marble", 1.0, 5, 6),
                                                       (2, None, "marble", 1.0, 6, 7)])
    return mandel, nebula, rendered


def test_renders_only_missing_images(cache):
    mandel, nebula, rendered = cache
    nebula.mkdir(parents=True)
    pygame.image.save(pygame.Surface((4, 4)), str(nebula / "marble.png"))
    assert prerender.main([]) == 0
    assert sorted(v[2] if len(v) == 6 and v[1] is None else v[4] for v in rendered) == ["teal-marble", "zoom"]
    assert (nebula / "teal-marble.png").is_file() and (mandel / "zoom-purple.png").is_file()


def test_nothing_to_do_when_everything_is_cached(cache, capsys):
    _mandel, _nebula, rendered = cache
    prerender.main([])
    rendered.clear()
    assert prerender.main([]) == 0
    assert rendered == []
    assert "already has a cached image" in capsys.readouterr().out


def test_only_renders_that_style_even_if_cached(cache):
    _mandel, nebula, rendered = cache
    prerender.main([])
    rendered.clear()
    assert prerender.main(["--only", "teal-marble"]) == 0
    assert [v[2] for v in rendered] == ["teal-marble"]


def test_unknown_style_is_refused(cache):
    _mandel, _nebula, rendered = cache
    assert prerender.main(["--only", "no-such-style"]) == 2
    assert rendered == []


def test_no_partial_file_is_left_behind(cache):
    _mandel, nebula, _rendered = cache
    prerender.main([])
    assert not [p for p in os.listdir(nebula) if ".part" in p]
