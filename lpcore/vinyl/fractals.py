"""Fractal & nebula vinyl generation, plus the per-album style picker.

Pure rendering functions (no Display/Qt dependency): they generate mandelbrot,
nebula, julia and munafo vinyl/label surfaces (caching the results as PNGs), and
_pick_vinyl_style maps an album + override to a concrete style. Shared by lp's
display and lp-deck via lpcore.
"""
import math
import os
import random

import numpy as np
import pygame

from lpcore.vinyl.catalog import (
    JULIA_VARIANTS, MANDELBROT_COLORS, MANDELBROT_VARIANTS, MANDELBROT_ZOOMS,
    MUNAFO_VARIANTS, PRERENDER_SIZE, STYLE_DISTRIBUTION, VINYL_COLORS)
from lpcore.vinyl.cache import (
    CACHE_DIR, JULIA_CACHE_DIR, MUNAFO_CACHE_DIR, MUNAFO_SOURCE_DIR, NEBULA_CACHE_DIR)


def _make_nebula_grids(seed, count=8, grid_size=64):
    """Generate value-noise grids for nebula rendering as numpy arrays."""
    rng = random.Random(seed)
    grids = []
    for _ in range(count):
        grid = np.array([[rng.random() for _ in range(grid_size + 1)]
                         for _ in range(grid_size + 1)], dtype=np.float64)
        grids.append((grid_size, grid))
    return grids

def _smoothstep(t):
    return t * t * (3 - 2 * t)

def _noise2d(x, y, gi, grids):
    """Vectorized 2D value noise. x, y are numpy arrays of the same shape."""
    g, grid = grids[gi % len(grids)]
    x = np.mod(x, g)
    y = np.mod(y, g)
    ix = x.astype(np.int32)
    iy = y.astype(np.int32)
    fx = _smoothstep(x - ix)
    fy = _smoothstep(y - iy)
    ix2 = (ix + 1) % g
    iy2 = (iy + 1) % g
    return (grid[iy, ix] * (1 - fx) * (1 - fy) +
            grid[iy, ix2] * fx * (1 - fy) +
            grid[iy2, ix] * (1 - fx) * fy +
            grid[iy2, ix2] * fx * fy)

def _fbm(x, y, octaves, gi, grids):
    """Vectorized fractal Brownian motion."""
    val = np.zeros_like(x)
    amp = 0.5
    freq = 1.0
    for o in range(octaves):
        val += amp * _noise2d(x * freq, y * freq, gi + o, grids)
        amp *= 0.55
        freq *= 2.1
    return val

def _nebula_purple_fire(br, blend, t1, t2, t3, hs):
    r1 = br * (40 + 200 * t1)
    g1 = br * (10 + 60 * hs)
    b1 = br * (120 + 135 * (0.5 + 0.5 * np.sin(t1 * 10.0)))
    r2 = br * (200 + 55 * t3)
    g2 = br * (80 + 140 * t1)
    b2 = br * (5 + 40 * (1 - t3))
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_ocean_emerald(br, blend, t1, t2, t3, hs):
    r1 = br * (5 + 50 * hs)
    g1 = br * (80 + 175 * t1)
    b1 = br * (60 + 140 * (0.5 + 0.5 * np.sin(t1 * 8.0)))
    r2 = br * (10 + 40 * t3)
    g2 = br * (40 + 80 * hs)
    b2 = br * (140 + 115 * t1)
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_crimson_gold(br, blend, t1, t2, t3, hs):
    r1 = br * (180 + 75 * t1)
    g1 = br * (15 + 50 * t1)
    b1 = br * (10 + 30 * hs)
    r2 = br * (200 + 55 * t3)
    g2 = br * (140 + 100 * t1)
    b2 = br * (5 + 20 * (1 - t3))
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_electric(br, blend, t1, t2, t3, hs):
    r1 = br * (20 + 60 * hs)
    g1 = br * (100 + 155 * t1)
    b1 = br * (180 + 75 * (0.5 + 0.5 * np.sin(t1 * 6.0)))
    r2 = br * (200 + 55 * t1)
    g2 = br * (20 + 60 * (1 - t3))
    b2 = br * (120 + 100 * hs)
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_emerald_purple(br, blend, t1, t2, t3, hs):
    r1 = br * (10 + 40 * hs)
    g1 = br * (120 + 135 * t1)
    b1 = br * (30 + 60 * t3)
    r2 = br * (100 + 120 * t1)
    g2 = br * (10 + 40 * hs)
    b2 = br * (140 + 115 * (0.5 + 0.5 * np.sin(t1 * 8.0)))
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_deep_emerald(br, blend, t1, t2, t3, hs):
    """No brightness multiplier — noise only shifts hue within green."""
    r = 40 + 30 * blend + 20 * hs
    g = 150 + 60 * t1 + 30 * blend
    b = 65 + 40 * t3 + 20 * (1 - blend)
    return (r, g, b)

def _nebula_bone(br, blend, t1, t2, t3, hs):
    base = 0.4 + 0.6 * br
    r1 = base * (220 + 35 * t1)
    g1 = base * (210 + 30 * hs)
    b1 = base * (185 + 40 * t3)
    r2 = base * (190 + 40 * t3)
    g2 = base * (175 + 35 * t1)
    b2 = base * (155 + 30 * hs)
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_cream_rose(br, blend, t1, t2, t3, hs):
    base = 0.4 + 0.6 * br
    r1 = base * (240 + 15 * t1)
    g1 = base * (215 + 20 * hs)
    b1 = base * (200 + 25 * t3)
    r2 = base * (220 + 35 * t1)
    g2 = base * (160 + 50 * hs)
    b2 = base * (165 + 50 * t3)
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_diamond_morning(br, blend, t1, t2, t3, hs):
    # Soft pink dawn clouds: rosy pink puffs over a pale pink-cream sky with
    # just a hint of blue. Kept airy/pastel (high base) for a dreamy label look.
    base = 0.88 + 0.12 * br
    # Very light, airy pink cloud tone (lots of white in it)
    r1 = base * (253 + 2 * t1)
    g1 = base * (226 + 14 * hs)
    b1 = base * (233 + 12 * t3)
    # Clear sky-blue in the gaps between clouds (matches the album's sky)
    r2 = base * (156 + 30 * t3)
    g2 = base * (210 + 16 * hs)
    b2 = base * (238 + 14 * t1)
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _clouds_palette(cloud, sky):
    """Build a soft-clouds palette function from a (cloud_rgb, sky_rgb) pair.

    Same airy structure as _nebula_diamond_morning — clouds at high blend, sky
    in the gaps — just parameterized by color so we can spin up colorways.
    """
    cr, cg, cb = cloud
    sr, sg, sb = sky

    def fn(br, blend, t1, t2, t3, hs):
        base = 0.88 + 0.12 * br
        r1 = base * (cr + 2 * t1)
        g1 = base * (cg + 14 * hs)
        b1 = base * (cb + 12 * t3)
        r2 = base * (sr + 30 * t3)
        g2 = base * (sg + 16 * hs)
        b2 = base * (sb + 14 * t1)
        return (r1 * blend + r2 * (1 - blend),
                g1 * blend + g2 * (1 - blend),
                b1 * blend + b2 * (1 - blend))

    return fn

def _nebula_marble(br, blend, t1, t2, t3, hs):
    base = 0.35 + 0.65 * br
    r1 = base * (230 + 25 * hs)
    g1 = base * (232 + 23 * t1)
    b1 = base * (240 + 15 * t3)
    r2 = base * (140 + 60 * t3)
    g2 = base * (145 + 55 * t1)
    b2 = base * (160 + 60 * hs)
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_cream_green(br, blend, t1, t2, t3, hs):
    base = 0.4 + 0.6 * (0.2 + 0.65 * t1 + 0.3 * t2)
    r1 = base * (225 + 20 * t1)
    g1 = base * (230 + 20 * hs)
    b1 = base * (200 + 20 * t3)
    r2 = base * (185 + 25 * t3)
    g2 = base * (215 + 25 * t1)
    b2 = base * (175 + 20 * hs)
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_galaxy(br, blend, t1, t2, t3, hs):
    br2 = br * br
    r1 = br2 * (80 + 175 * t1)
    g1 = br2 * (30 + 80 * hs)
    b1 = br2 * (120 + 135 * (0.5 + 0.5 * np.sin(t1 * 8.0)))
    r2 = br2 * (20 + 60 * t3)
    g2 = br2 * (15 + 50 * t1)
    b2 = br2 * (80 + 160 * hs)
    star = np.maximum(0, t1 * t2 * 4 - 1.2) ** 2
    return (r1 * blend + r2 * (1 - blend) + star * 200,
            g1 * blend + g2 * (1 - blend) + star * 180,
            b1 * blend + b2 * (1 - blend) + star * 255)

def _nebula_galaxy_warm(br, blend, t1, t2, t3, hs):
    br2 = br * br
    r1 = br2 * (160 + 95 * t1)
    g1 = br2 * (20 + 80 * hs)
    b1 = br2 * (100 + 120 * t3)
    r2 = br2 * (180 + 75 * t3)
    g2 = br2 * (80 + 120 * t1)
    b2 = br2 * (15 + 40 * hs)
    star = np.maximum(0, t1 * t2 * 4 - 1.2) ** 2
    return (r1 * blend + r2 * (1 - blend) + star * 220,
            g1 * blend + g2 * (1 - blend) + star * 200,
            b1 * blend + b2 * (1 - blend) + star * 160)

def _nebula_galaxy_cold(br, blend, t1, t2, t3, hs):
    br2 = br * br
    r1 = br2 * (15 + 60 * hs)
    g1 = br2 * (80 + 140 * t1)
    b1 = br2 * (160 + 95 * (0.5 + 0.5 * np.sin(t1 * 6.0)))
    r2 = br2 * (30 + 50 * t3)
    g2 = br2 * (40 + 80 * t1)
    b2 = br2 * (130 + 125 * hs)
    star = np.maximum(0, t1 * t2 * 4 - 1.2) ** 2
    return (r1 * blend + r2 * (1 - blend) + star * 180,
            g1 * blend + g2 * (1 - blend) + star * 220,
            b1 * blend + b2 * (1 - blend) + star * 255)

def _nebula_oil_spill(br, blend, t1, t2, t3, hs):
    r1 = br * (60 + 90 * t1)
    g1 = br * (80 + 100 * hs)
    b1 = br * (100 + 80 * t3)
    r2 = br * (130 + 70 * t3)
    g2 = br * (50 + 60 * t1)
    b2 = br * (60 + 70 * hs)
    pop = np.maximum(0, t1 * t2 * 3 - 0.9)
    return (r1 * blend + r2 * (1 - blend) + pop * 80,
            g1 * blend + g2 * (1 - blend) + pop * 100,
            b1 * blend + b2 * (1 - blend) + pop * 90)

def _nebula_absinthe(br, blend, t1, t2, t3, hs):
    r1 = br * (60 + 80 * hs)
    g1 = br * (150 + 80 * t1)
    b1 = br * (30 + 50 * t3)
    r2 = br * (100 + 80 * t1)
    g2 = br * (30 + 50 * hs)
    b2 = br * (90 + 80 * t3)
    pop = np.maximum(0, t1 * t2 * 3 - 0.85)
    return (r1 * blend + r2 * (1 - blend) + pop * 120,
            g1 * blend + g2 * (1 - blend) + pop * 70,
            b1 * blend + b2 * (1 - blend) + pop * 30)

def _nebula_coral_reef(br, blend, t1, t2, t3, hs):
    r1 = br * (200 + 40 * t1)
    g1 = br * (90 + 60 * hs)
    b1 = br * (80 + 50 * t3)
    r2 = br * (40 + 60 * t3)
    g2 = br * (140 + 80 * t1)
    b2 = br * (130 + 70 * hs)
    pop = np.maximum(0, t1 * t2 * 3 - 0.9)
    return (r1 * blend + r2 * (1 - blend) + pop * 60,
            g1 * blend + g2 * (1 - blend) + pop * 90,
            b1 * blend + b2 * (1 - blend) + pop * 40)

def _nebula_bruise(br, blend, t1, t2, t3, hs):
    r1 = br * (80 + 80 * t1)
    g1 = br * (20 + 50 * hs)
    b1 = br * (120 + 100 * t3)
    r2 = br * (120 + 60 * t3)
    g2 = br * (110 + 60 * t1)
    b2 = br * (30 + 40 * hs)
    return (r1 * blend + r2 * (1 - blend),
            g1 * blend + g2 * (1 - blend),
            b1 * blend + b2 * (1 - blend))

def _nebula_molten(br, blend, t1, t2, t3, hs):
    r1 = br * (190 + 50 * t1)
    g1 = br * (80 + 70 * t1)
    b1 = br * (20 + 40 * hs)
    r2 = br * (140 + 60 * t3)
    g2 = br * (25 + 40 * hs)
    b2 = br * (50 + 60 * t1)
    pop = np.maximum(0, t1 * t2 * 3 - 0.85)
    return (r1 * blend + r2 * (1 - blend) + pop * 100,
            g1 * blend + g2 * (1 - blend) + pop * 120,
            b1 * blend + b2 * (1 - blend) + pop * 20)

def _nebula_lava_lamp(br, blend, t1, t2, t3, hs):
    r1 = br * (200 + 55 * t1)
    g1 = br * (40 + 80 * t1)
    b1 = br * (10 + 50 * hs)
    r2 = br * (120 + 80 * t3)
    g2 = br * (10 + 30 * hs)
    b2 = br * (140 + 115 * t1)
    pop = np.maximum(0, t1 * t2 * 3 - 0.9)
    return (r1 * blend + r2 * (1 - blend) + pop * 200,
            g1 * blend + g2 * (1 - blend) + pop * 180,
            b1 * blend + b2 * (1 - blend) + pop * 30)

# Nebula variants: (seed, palette_func, name, saturation, warp_octaves, arm_octaves)
# Most use standard noise settings; deep_emerald uses reduced warp/arm octaves
NEBULA_VARIANTS = [
    (42, _nebula_purple_fire,    'purple-fire',    1.5, 6, 7),
    (42, _nebula_ocean_emerald,  'ocean-emerald',  1.5, 6, 7),
    (77, _nebula_crimson_gold,   'crimson-gold',   1.5, 6, 7),
    (13, _nebula_electric,       'electric',       1.5, 6, 7),
    (99, _nebula_emerald_purple, 'emerald-purple', 1.5, 6, 7),
    (55, _nebula_deep_emerald,   'deep-emerald',   1.1, 3, 4),
    (63, _nebula_cream_green,    'cream-green',    1.2, 6, 7),
    (31, _nebula_bone,           'bone',           1.1, 6, 7),
    (17, _nebula_cream_rose,     'cream-rose',     1.2, 6, 7),
    (28, _nebula_diamond_morning,'diamond-morning',1.25, 6, 7, 'clouds'),
    (71, _clouds_palette((254, 206, 178), (158, 168, 214)), 'sunset-peach',  1.2, 6, 7, 'clouds'),
    (12, _clouds_palette((226, 208, 240), (160, 182, 234)), 'lavender-dusk', 1.2, 6, 7, 'clouds'),
    (90, _clouds_palette((214, 240, 222), (164, 214, 236)), 'mint-sky',      1.2, 6, 7, 'clouds'),
    (5,  _clouds_palette((252, 214, 204), (188, 196, 224)), 'rose-gold',     1.2, 6, 7, 'clouds'),
    (60, _clouds_palette((232, 230, 236), (146, 160, 182)), 'storm-grey',    1.15, 6, 7, 'clouds'),
    (33, _clouds_palette((250, 205, 232), (190, 200, 245)), 'cotton-candy',  1.2, 6, 7, 'clouds'),
    (47, _clouds_palette((252, 236, 196), (176, 208, 226)), 'butter-cream',  1.2, 6, 7, 'clouds'),
    (19, _clouds_palette((206, 240, 230), (150, 200, 220)), 'seafoam',       1.2, 6, 7, 'clouds'),
    (8,  _clouds_palette((252, 196, 168), (150, 150, 200)), 'ember-dusk',    1.2, 6, 7, 'clouds'),
    (52, _clouds_palette((224, 196, 226), (168, 170, 214)), 'plum-wine',     1.2, 6, 7, 'clouds'),
    (64, _clouds_palette((222, 240, 248), (150, 192, 224)), 'arctic',        1.2, 6, 7, 'clouds'),
    (88, _nebula_marble,         'marble',         1.2, 6, 7),
    (42, _nebula_galaxy,         'galaxy',         1.6, 6, 7),
    (71, _nebula_galaxy_warm,    'galaxy-warm',    1.5, 6, 7),
    (23, _nebula_galaxy_cold,    'galaxy-cold',    1.5, 6, 7),
    (33, _nebula_oil_spill,      'oil-spill',      1.8, 6, 7),
    (51, _nebula_absinthe,       'absinthe',       1.8, 6, 7),
    (44, _nebula_coral_reef,     'coral-reef',     1.8, 6, 7),
    (19, _nebula_bruise,         'bruise',         1.8, 6, 7),
    (67, _nebula_molten,         'molten',         1.8, 6, 7),
    (82, _nebula_lava_lamp,      'lava-lamp',      1.8, 6, 7),
]

def _render_clouds_surface(variant, size, cells=2.6, octaves=4):
    """Render soft painterly clouds at FULL resolution (no half-res upscale, so
    it's crisp not blurry): pink clouds up top fading to clear blue sky below,
    with sunlit white tops. `cells` controls how many cloud masses span the disc
    (lower = calmer); `octaves` adds fine wisp detail.
    """
    seed, palette_fn, _name, sat = variant[:4]
    grids = _make_nebula_grids(seed)

    d = size * 2
    py, px = np.mgrid[0:d, 0:d].astype(np.float64)
    dx = px - size
    dy = py - size
    dist = np.sqrt(dx * dx + dy * dy)

    nx = px / d * cells
    ny = py / d * cells
    c1 = _fbm(nx, ny, octaves, 0, grids)
    c2 = _fbm(nx + 5.0, ny + 5.0, octaves, 3, grids)

    # fBm sits roughly in [0.2, 0.75]; stretch to span 0..1 for full contrast.
    t1 = np.clip((c1 - 0.25) * 2.4, 0.0, 1.0)
    t3 = np.clip((c2 - 0.25) * 2.4, 0.0, 1.0)
    brightness = np.clip(0.6 + 0.45 * t1, 0.0, 1.0)

    # Reads as clouds, not a gradient: cloud DENSITY drives most of the pink,
    # with a gentle top-pink / bottom-blue lean.
    vert = py / float(d)                          # 0 = top, 1 = bottom
    pinkness = t1 * 1.3 + (1.0 - vert) * 0.95 + 0.28
    blend = _smoothstep(np.clip(pinkness, 0.0, 1.0))

    r, g, b = palette_fn(brightness, blend, t1, t3, t3, t3)

    avg = (r + g + b) / 3.0
    r = avg + (r - avg) * sat
    g = avg + (g - avg) * sat
    b = avg + (b - avg) * sat

    # Faint lift on the densest wisps only — keep them light pink, not a white
    # blob (small, high threshold, low strength).
    hi = np.clip((t1 - 0.75) * 3.0, 0.0, 1.0) ** 1.6
    r = r + (255 - r) * hi * 0.22
    g = g + (255 - g) * hi * 0.22
    b = b + (255 - b) * hi * 0.22

    # Anti-aliased disc edge (1px soft rim), full-resolution alpha.
    alpha = np.clip(size - dist + 0.5, 0.0, 1.0)
    a = (alpha * 255.0).astype(np.uint8)
    r = np.clip(r, 0, 255).astype(np.uint8)
    g = np.clip(g, 0, 255).astype(np.uint8)
    b = np.clip(b, 0, 255).astype(np.uint8)

    rgba = np.stack([r, g, b, a], axis=-1).tobytes()
    return pygame.image.frombuffer(rgba, (d, d), 'RGBA').copy()

def _render_nebula_surface(variant, size):
    """Render a nebula-style vinyl disc. Vectorized over the full pixel grid."""
    seed, palette_fn, _name, sat, warp_oct, arm_oct = variant[:6]
    # Some variants opt into the soft-clouds renderer instead of the swirly
    # nebula look (7th tuple element == 'clouds').
    if len(variant) > 6 and variant[6] == 'clouds':
        return _render_clouds_surface(variant, size)
    grids = _make_nebula_grids(seed)

    d = size * 2
    sm = max(size // 2, 40)
    d_sm = sm * 2
    sc = sm
    max_r_sq = (sm * 0.95) ** 2

    py, px = np.mgrid[0:d_sm, 0:d_sm].astype(np.float64)
    dx = px - sc
    dy = py - sc
    inside = dx * dx + dy * dy <= max_r_sq
    dist = np.sqrt(dx * dx + dy * dy) / sm
    angle = np.arctan2(dy, dx)

    nx = px / sm * 3.0
    ny = py / sm * 3.0

    wx = nx + _fbm(nx + 1.7, ny + 9.2, warp_oct, 0, grids) * 3.0
    wy = ny + _fbm(nx + 8.3, ny + 2.8, warp_oct, 2, grids) * 3.0
    wx2 = wx + _fbm(wx * 0.8 + 3.1, wy * 0.8 + 7.7, max(warp_oct - 1, 2), 4, grids) * 2.0
    wy2 = wy + _fbm(wx * 0.8 + 1.3, wy * 0.8 + 4.9, max(warp_oct - 1, 2), 6, grids) * 2.0

    sa = np.sin(angle * 2.0) * dist * 2.5
    ca = np.cos(angle * 2.0) * dist * 2.5
    arm = _fbm(wx2 + sa, wy2 + ca, arm_oct, 1, grids)
    cloud1 = _fbm(wx2 * 1.2, wy2 * 1.2, arm_oct, 3, grids)
    cloud2 = _fbm(wx2 * 0.7 + 20, wy2 * 0.7 + 20, max(arm_oct - 1, 3), 5, grids)

    t1, t2, t3 = arm, cloud1, cloud2
    brightness = 0.2 + 0.65 * t1 + 0.3 * t2
    brightness *= (1.0 - dist * 0.3)
    brightness = np.clip((brightness - 0.15) * 1.4, 0.0, 1.0)
    hue_shift = _fbm(nx * 0.8, ny * 0.8, 3, 0, grids)
    blend = _smoothstep(np.clip((t1 - 0.3) * 2.5, 0.0, 1.0))

    r, g, b = palette_fn(brightness, blend, t1, t2, t3, hue_shift)

    avg = (r + g + b) / 3.0
    r = avg + (r - avg) * sat
    g = avg + (g - avg) * sat
    b = avg + (b - avg) * sat

    core_mask = dist < 0.2
    core = np.where(core_mask, (1 - dist / 0.2) ** 2, 0.0)
    r = r + core * (255 - r) * 0.7
    g = g + core * (220 - g) * 0.5
    b = b + core * (255 - b) * 0.6

    r = np.where(inside, np.clip(r, 0, 255), 0).astype(np.uint8)
    g = np.where(inside, np.clip(g, 0, 255), 0).astype(np.uint8)
    b = np.where(inside, np.clip(b, 0, 255), 0).astype(np.uint8)
    a = np.where(inside, 255, 0).astype(np.uint8)

    rgba = np.stack([r, g, b, a], axis=-1).tobytes()
    surf = pygame.image.frombuffer(rgba, (d_sm, d_sm), 'RGBA').copy()

    # Blur and upscale
    blur1 = d // 2
    result = pygame.transform.smoothscale(surf, (blur1, blur1))
    result = pygame.transform.smoothscale(result, (d, d))
    # Mask to disc
    mask = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (size, size), size)
    result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return result

def _render_mandelbrot_surface(variant, size):
    """Render a mandelbrot fractal disc. Vectorized escape-time over the full grid."""
    cx_m, cy_m, zoom, max_iter, _name, color_key = variant
    scheme = MANDELBROT_COLORS.get(color_key, MANDELBROT_COLORS['purple'])
    base_dark, r_p, g_p, b_p, _groove, _track = scheme

    d = size * 2
    sm = max(size // 2, 40)
    d_sm = sm * 2
    sc = sm
    max_r_sq = (sm * 0.95) ** 2

    py, px = np.mgrid[0:d_sm, 0:d_sm].astype(np.float64)
    dx = px - sc
    dy = py - sc
    inside = dx * dx + dy * dy <= max_r_sq

    c = (cx_m + dx / sm / zoom) + 1j * (cy_m + dy / sm / zoom)
    z = np.zeros_like(c)
    iters = np.full(c.shape, max_iter, dtype=np.int32)
    active = inside.copy()

    for step in range(max_iter):
        z = np.where(active, z * z + c, z)
        escaped = active & (z.real * z.real + z.imag * z.imag > 4.0)
        iters[escaped] = step + 1
        active = active & ~escaped
        if not active.any():
            break

    t = iters.astype(np.float64) / max_iter
    r_arr = r_p[0] + r_p[1] * (0.5 + 0.5 * np.sin(t * r_p[2] + r_p[3]))
    g_arr = g_p[0] + g_p[1] * (0.5 + 0.5 * np.sin(t * g_p[2] + g_p[3]))
    b_arr = b_p[0] + b_p[1] * (0.5 + 0.5 * np.sin(t * b_p[2] + b_p[3]))

    # Interior pixels (never escaped) get base_dark
    interior = iters == max_iter
    r_arr = np.where(interior, base_dark[0], r_arr)
    g_arr = np.where(interior, base_dark[1], g_arr)
    b_arr = np.where(interior, base_dark[2], b_arr)

    r_arr = np.where(inside, np.clip(r_arr, 0, 255), 0).astype(np.uint8)
    g_arr = np.where(inside, np.clip(g_arr, 0, 255), 0).astype(np.uint8)
    b_arr = np.where(inside, np.clip(b_arr, 0, 255), 0).astype(np.uint8)
    a_arr = np.where(inside, 255, 0).astype(np.uint8)

    rgba = np.stack([r_arr, g_arr, b_arr, a_arr], axis=-1).tobytes()
    sm_surf = pygame.image.frombuffer(rgba, (d_sm, d_sm), 'RGBA').copy()

    # Blur
    blur1 = d // 2
    result = pygame.transform.smoothscale(sm_surf, (blur1, blur1))
    result = pygame.transform.smoothscale(result, (d, d))
    # Mask to disc
    center = (size, size)
    mask = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), center, size)
    result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return result

def _render_munafo_surface(variant, size):
    """Load a locked Munafo deep-zoom snapshot and scale it to vinyl size.
    The snapshot in munafo_work/configs/<name>.png is the source of truth;
    we never re-run the perturbation engine here."""
    config_name = variant[0]
    src_path = os.path.join(MUNAFO_SOURCE_DIR, f'{config_name}.png')
    d = size * 2
    img = pygame.image.load(src_path).convert_alpha()
    surf = pygame.transform.smoothscale(img, (d, d))
    # The snapshot already has a disc-masked alpha (black outside the
    # circle), but ensure the mask is clean at the output resolution.
    mask = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (size, size), size)
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return surf

def _render_julia_surface(variant, size):
    """Render a Julia set disc. Each pixel = initial z, c is fixed.
    Rainbow sinusoidal palette."""
    cr, ci, zoom, max_iter, _name = variant
    c = complex(cr, ci)

    d = size * 2
    sm = max(size // 2, 40)
    d_sm = sm * 2
    sc = sm
    max_r_sq = (sm * 0.95) ** 2

    py, px = np.mgrid[0:d_sm, 0:d_sm].astype(np.float64)
    dx = px - sc
    dy = py - sc
    inside = dx * dx + dy * dy <= max_r_sq

    z = (dx / sm / zoom) + 1j * (dy / sm / zoom)
    iters = np.full(z.shape, max_iter, dtype=np.int32)
    active = inside.copy()

    for step in range(max_iter):
        z = np.where(active, z * z + c, z)
        escaped = active & (z.real * z.real + z.imag * z.imag > 4.0)
        iters[escaped] = step + 1
        active = active & ~escaped
        if not active.any():
            break

    t = iters.astype(np.float64) / max_iter

    # Rainbow sinusoidal palette
    r_arr = (np.sin(t * 8.0) * 0.5 + 0.5) * 255
    g_arr = (np.sin(t * 8.0 + 2.0) * 0.5 + 0.5) * 200
    b_arr = (np.sin(t * 8.0 + 4.0) * 0.5 + 0.5) * 255

    # Interior: dark purple
    interior = iters == max_iter
    r_arr = np.where(interior, 10, r_arr)
    g_arr = np.where(interior, 5, g_arr)
    b_arr = np.where(interior, 25, b_arr)

    r_arr = np.where(inside, np.clip(r_arr, 0, 255), 0).astype(np.uint8)
    g_arr = np.where(inside, np.clip(g_arr, 0, 255), 0).astype(np.uint8)
    b_arr = np.where(inside, np.clip(b_arr, 0, 255), 0).astype(np.uint8)
    a_arr = np.where(inside, 255, 0).astype(np.uint8)

    rgba = np.stack([r_arr, g_arr, b_arr, a_arr], axis=-1).tobytes()
    sm_surf = pygame.image.frombuffer(rgba, (d_sm, d_sm), 'RGBA').copy()

    blur1 = d // 2
    result = pygame.transform.smoothscale(sm_surf, (blur1, blur1))
    result = pygame.transform.smoothscale(result, (d, d))
    mask = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (size, size), size)
    result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return result

def prerender_all():
    """Pre-render all mandelbrot, nebula, and munafo variants to PNG cache.
    Run once on a fast machine. Munafo variants downsample from their
    high-res (9000x9000) gold archives in munafo_work/configs/ — the deep
    zoom detail is preserved because we shrink already-resolved pixels
    rather than re-running the math at low resolution."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    for variant in MANDELBROT_VARIANTS:
        name = variant[4]
        color = variant[5]
        cache_name = f'{name}-{color}'
        path = os.path.join(CACHE_DIR, f'{cache_name}.png')
        print(f'  rendering mandelbrot/{cache_name} at {PRERENDER_SIZE}px radius...', end=' ', flush=True)
        surf = _render_mandelbrot_surface(variant, PRERENDER_SIZE)
        pygame.image.save(surf, path)
        print('done')
    print(f'cached {len(MANDELBROT_VARIANTS)} mandelbrot variants in {CACHE_DIR}')

    if os.path.isdir(MUNAFO_SOURCE_DIR):
        os.makedirs(MUNAFO_CACHE_DIR, exist_ok=True)
        for variant in MUNAFO_VARIANTS:
            config_name = variant[0]
            path = os.path.join(MUNAFO_CACHE_DIR, f'{config_name}.png')
            print(f'  downsampling munafo/{config_name} to {PRERENDER_SIZE}px radius...',
                  end=' ', flush=True)
            surf = _render_munafo_surface(variant, PRERENDER_SIZE)
            pygame.image.save(surf, path)
            print('done')
        print(f'cached {len(MUNAFO_VARIANTS)} munafo variants in {MUNAFO_CACHE_DIR}')
    else:
        print(f'  skipping munafo prerender — gold archives not found at '
              f'{MUNAFO_SOURCE_DIR}')
        print(f'  (committed cache at {MUNAFO_CACHE_DIR} will still be used '
              f'at runtime; clone the bongsweat repo as a sibling to regenerate)')

    os.makedirs(NEBULA_CACHE_DIR, exist_ok=True)
    for variant in NEBULA_VARIANTS:
        name = variant[2]
        path = os.path.join(NEBULA_CACHE_DIR, f'{name}.png')
        print(f'  rendering nebula/{name} at {PRERENDER_SIZE}px radius...', end=' ', flush=True)
        surf = _render_nebula_surface(variant, PRERENDER_SIZE)
        pygame.image.save(surf, path)
        print('done')
    print(f'cached {len(NEBULA_VARIANTS)} nebula variants in {NEBULA_CACHE_DIR}')

    # Julia labels — rendered smaller (~label size, not full record).
    os.makedirs(JULIA_CACHE_DIR, exist_ok=True)
    julia_size = 400
    for variant in JULIA_VARIANTS:
        name = variant[4]
        path = os.path.join(JULIA_CACHE_DIR, f'{name}.png')
        print(f'  rendering julia/{name} at {julia_size}px radius...', end=' ', flush=True)
        surf = _render_julia_surface(variant, julia_size)
        pygame.image.save(surf, path)
        print('done')
    print(f'cached {len(JULIA_VARIANTS)} julia variants in {JULIA_CACHE_DIR}')

def _pick_vinyl_style(album_path, override='random'):
    """Pick a vinyl style. If override is set, use that; otherwise random per album."""
    rng = random.Random(album_path)

    if override == 'random':
        total = sum(w for _, w in STYLE_DISTRIBUTION)
        roll = rng.randint(0, total - 1)
        style_type = 'black'
        cumulative = 0
        for stype, weight in STYLE_DISTRIBUTION:
            cumulative += weight
            if roll < cumulative:
                style_type = stype
                break
    elif override in ('clear', 'picture'):
        style_type = override
    elif override == 'black':
        style_type = 'black'
    elif override.startswith('color'):
        style_type = 'color'
    elif override.startswith('mandelbrot'):
        style_type = 'mandelbrot'
    elif override.startswith('nebula'):
        style_type = 'nebula'
    elif override.startswith('munafo'):
        style_type = 'munafo'
    elif override.startswith('pattern'):
        style_type = 'pattern'
    else:
        style_type = 'black'

    if style_type == 'black':
        return {'type': 'black'}
    elif style_type == 'color':
        if override.startswith('color-'):
            color_name = override[len('color-'):]
            if color_name in VINYL_COLORS:
                return {'type': 'color', 'color': color_name}
        color_name = rng.choice(list(VINYL_COLORS.keys()))
        return {'type': 'color', 'color': color_name}
    elif style_type == 'mandelbrot':
        if override.startswith('mandelbrot-'):
            spec = override[len('mandelbrot-'):]
            # Check for zoom-color combo (e.g. "seahorse-purple")
            for v in MANDELBROT_VARIANTS:
                if f'{v[4]}-{v[5]}' == spec:
                    return {'type': 'mandelbrot', 'variant': v}
            # Check for color only (e.g. "purple") — random zoom in that color
            if spec in MANDELBROT_COLORS:
                color_variants = [v for v in MANDELBROT_VARIANTS if v[5] == spec]
                return {'type': 'mandelbrot', 'variant': rng.choice(color_variants)}
            # Check for zoom only (e.g. "seahorse") — random color for that zoom
            for z in MANDELBROT_ZOOMS:
                if z[4] == spec:
                    zoom_variants = [v for v in MANDELBROT_VARIANTS if v[4] == spec]
                    return {'type': 'mandelbrot', 'variant': rng.choice(zoom_variants)}
        variant = rng.choice(MANDELBROT_VARIANTS)
        return {'type': 'mandelbrot', 'variant': variant}
    elif style_type == 'nebula':
        if override.startswith('nebula-'):
            variant_name = override[len('nebula-'):]
            for v in NEBULA_VARIANTS:
                if v[2] == variant_name:
                    return {'type': 'nebula', 'variant': v}
        variant = rng.choice(NEBULA_VARIANTS)
        return {'type': 'nebula', 'variant': variant}
    elif style_type == 'munafo':
        # Accept "munafo", "munafo-deep5_v1", or "munafo-deep5".
        if override.startswith('munafo-'):
            spec = override[len('munafo-'):]
            for v in MUNAFO_VARIANTS:
                if v[0] == spec or v[1] == f'munafo-{spec}' or v[0].startswith(spec):
                    return {'type': 'munafo', 'variant': v}
        variant = rng.choice(MUNAFO_VARIANTS)
        return {'type': 'munafo', 'variant': variant}
    elif style_type == 'pattern':
        # Picture-disc with a fractal body. Override forms:
        #   pattern                       — random fractal
        #   pattern-mandelbrot            — random mandelbrot
        #   pattern-mandelbrot-X-Y        — specific mandelbrot
        #   pattern-nebula / -nebula-X    — nebula
        #   pattern-munafo  / -munafo-X   — munafo
        sub_type = None
        sub_variant = None
        if override == 'pattern':
            sub_type = rng.choice(['mandelbrot', 'nebula', 'munafo'])
        elif override.startswith('pattern-mandelbrot'):
            sub_type = 'mandelbrot'
            spec = override[len('pattern-mandelbrot'):].lstrip('-')
            if spec:
                for v in MANDELBROT_VARIANTS:
                    if f'{v[4]}-{v[5]}' == spec:
                        sub_variant = v
                        break
        elif override.startswith('pattern-nebula'):
            sub_type = 'nebula'
            spec = override[len('pattern-nebula'):].lstrip('-')
            if spec:
                for v in NEBULA_VARIANTS:
                    if v[2] == spec:
                        sub_variant = v
                        break
        elif override.startswith('pattern-munafo'):
            sub_type = 'munafo'
            spec = override[len('pattern-munafo'):].lstrip('-')
            if spec:
                for v in MUNAFO_VARIANTS:
                    if v[0] == spec or v[0].startswith(spec):
                        sub_variant = v
                        break
        else:
            sub_type = rng.choice(['mandelbrot', 'nebula', 'munafo'])

        if sub_variant is None:
            if sub_type == 'mandelbrot':
                sub_variant = rng.choice(MANDELBROT_VARIANTS)
            elif sub_type == 'nebula':
                sub_variant = rng.choice(NEBULA_VARIANTS)
            elif sub_type == 'munafo':
                sub_variant = rng.choice(MUNAFO_VARIANTS)
        return {'type': 'pattern',
                'sub': {'type': sub_type, 'variant': sub_variant}}
    elif style_type == 'clear':
        return {'type': 'clear'}
    elif style_type == 'picture':
        return {'type': 'picture'}

    return {'type': 'black'}
