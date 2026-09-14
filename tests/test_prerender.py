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
    prerender.main([])
    rendered.clear()
    os.unlink(nebula / "marble.png")
    assert prerender.main([]) == 0
    assert [v[2] for v in rendered] == ["marble"]
    assert (nebula / "teal-marble.png").is_file() and (mandel / "zoom-purple.png").is_file()


def test_an_image_with_no_recorded_key_is_rendered_again(cache):
    """A cache from before keys existed: nothing says what it was rendered
    from, so it is treated as out of date once, then recorded."""
    _mandel, nebula, rendered = cache
    nebula.mkdir(parents=True)
    pygame.image.save(pygame.Surface((4, 4)), str(nebula / "marble.png"))
    assert prerender.main([]) == 0
    assert "marble" in [v[2] for v in rendered if len(v) == 6]


def test_nothing_to_do_when_everything_is_cached(cache, capsys):
    _mandel, _nebula, rendered = cache
    prerender.main([])
    rendered.clear()
    assert prerender.main([]) == 0
    assert rendered == []
    assert "already has a current cached image" in capsys.readouterr().out


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


# --- per-style keys: render what changed, and only that ---------------------------

def _render_a(variant, size):
    return pygame.Surface((4, 4), pygame.SRCALPHA)


def _render_b(variant, size):
    return pygame.Surface((5, 5), pygame.SRCALPHA)     # different source text


def test_a_retuned_style_renders_again_and_the_others_do_not(cache, monkeypatch):
    _mandel, _nebula, rendered = cache
    prerender.main([])
    rendered.clear()
    monkeypatch.setattr(prerender, "NEBULA_VARIANTS", [(1, None, "teal-marble", 1.0, 5, 6),
                                                       (2, None, "marble", 1.3, 6, 7)])
    assert prerender.main([]) == 0
    assert [v[2] for v in rendered] == ["marble"]
    rendered.clear()
    assert prerender.main([]) == 0
    assert rendered == [], "recorded as current once rendered"


def test_a_palette_function_is_a_parameter_too(cache, monkeypatch):
    _mandel, _nebula, rendered = cache
    prerender.main([])
    rendered.clear()
    monkeypatch.setattr(prerender, "NEBULA_VARIANTS", [(1, _render_a, "teal-marble", 1.0, 5, 6),
                                                       (2, None, "marble", 1.0, 6, 7)])
    prerender.main([])
    assert [v[2] for v in rendered] == ["teal-marble"]


def test_editing_the_renderer_renders_its_whole_family(cache, monkeypatch):
    _mandel, _nebula, rendered = cache
    monkeypatch.setattr(prerender, "_render_nebula_surface", _render_a)
    prerender.main([])
    rendered.clear()
    monkeypatch.setattr(prerender, "_render_nebula_surface", _render_b)
    prerender.main([])
    assert rendered == [], "the stub records nothing, so check the files instead"
    assert pygame.image.load(str(_nebula / "marble.png")).get_size() == (5, 5)
    assert pygame.image.load(str(_nebula / "teal-marble.png")).get_size() == (5, 5)
    assert not (_mandel / ".keys.json").exists() or \
        pygame.image.load(str(_mandel / "zoom-purple.png")).get_size() == (4, 4)


def test_keys_are_stable_across_processes_and_size_aware():
    from lpcore.vinyl import fractals
    v = fractals.NEBULA_VARIANTS[0]
    k1 = prerender.style_key(fractals._render_nebula_surface, v)
    k2 = prerender.style_key(fractals._render_nebula_surface, v)
    assert k1 == k2
    assert prerender.style_key(fractals._render_nebula_surface, v, size=400) != k1
    assert prerender.style_key(fractals._render_mandelbrot_surface, v) != k1


def test_the_real_renderers_fingerprint_reaches_their_helpers():
    from lpcore.vinyl import fractals
    text = prerender.renderer_fingerprint(fractals._render_nebula_surface)
    assert "def _render_smoke_layers_surface" in text
    assert "SMOKE_LAYER_PARAMS=" in text
    assert "_FIELD_CACHE_BYTES" not in text.split("def ")[0], "cache sizing is not a parameter"


def test_check_reports_stale_styles_without_rendering(cache, monkeypatch, capsys):
    _mandel, _nebula, rendered = cache
    assert prerender.main(["--check"]) == 1
    assert rendered == []
    assert "teal-marble: new" in capsys.readouterr().out
    prerender.main([])
    assert prerender.main(["--check"]) == 0
    monkeypatch.setattr(prerender, "NEBULA_VARIANTS", [(1, None, "teal-marble", 2.0, 5, 6),
                                                       (2, None, "marble", 1.0, 6, 7)])
    assert prerender.main(["--check"]) == 1
    assert "teal-marble: changed" in capsys.readouterr().out


def test_no_partial_file_is_left_behind(cache):
    _mandel, nebula, _rendered = cache
    prerender.main([])
    assert not [p for p in os.listdir(nebula) if ".part" in p]
    assert sorted(os.listdir(nebula)) == [".keys.json", "marble.png", "teal-marble.png"]
