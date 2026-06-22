import io
import math
import os
import random
import threading
import time
import numpy as np
import pygame
import pygame.gfxdraw
from pygame._sdl2 import video as sdl2_video


DARK_BG = (17, 17, 17)
PANEL_BG = (22, 22, 22)
TEXT_COLOR = (230, 230, 230)
DIM_TEXT = (80, 80, 80)
ACCENT = (200, 200, 200)
VINYL_LABEL = (140, 90, 60)
VINYL_LABEL_DARK = (100, 65, 40)

# Label color presets: (main_color, accent_color)
LABEL_COLORS = {
    'brown':    ((140, 90, 60),   (100, 65, 40)),
    'black':    ((30, 30, 30),    (20, 20, 20)),
    'white':    ((230, 230, 225), (190, 190, 185)),
    'cream':    ((210, 200, 170), (170, 162, 135)),
    'red':      ((160, 40, 40),   (120, 28, 28)),
    'orange':   ((180, 100, 30),  (140, 75, 20)),
    'yellow':   ((200, 185, 50),  (160, 148, 35)),
    'green':    ((40, 130, 55),   (28, 95, 38)),
    'blue':     ((45, 60, 150),   (32, 42, 110)),
    'purple':   ((100, 45, 140),  (72, 32, 100)),
}
NEEDLE_COLOR = (200, 200, 200)

# Little decorative critters for the label's empty spaces (rendered via the
# Noto Color Emoji font). 2 per label.
DECOR_EMOJI = {
    'bird': '🐦', 'dove': '🕊', 'owl': '🦉',
    'sun': '☀', 'moon': '🌙', 'star': '⭐',
    'octopus': '🐙', 'fish': '🐟',
    'beaver': '🦫', 'dog': '🐕', 'cat': '🐈',
}


def _resolve_color(val, fallback):
    """'auto'/None → fallback accent; '#rrggbb' → rgb tuple."""
    if isinstance(val, str) and val.startswith('#') and len(val) == 7:
        try:
            return (int(val[1:3], 16), int(val[3:5], 16), int(val[5:7], 16))
        except ValueError:
            pass
    return tuple(fallback[:3])

# Record geometry (as fraction of record radius)
OUTER_GROOVE = 0.92
INNER_GROOVE = 0.35
LABEL_RADIUS = 0.30

# Vinyl base style: (base_color, groove_color, track_mark_color)
VINYL_BLACK = ((40, 40, 40), (46, 46, 46), (58, 58, 58))

# Colored vinyl variants — same structure as VINYL_BLACK
VINYL_COLORS = {
    'red':          (130, 35, 35),
    'navy':         (40, 50, 120),
    'forest':       (35, 100, 50),
    'plum':         (110, 40, 95),
    'chocolate':    (120, 65, 30),
    'slate':        (80, 90, 105),
    'amber':        (140, 95, 25),
    'teal':         (30, 110, 110),
    'burgundy':     (115, 30, 55),
    'olive':        (90, 100, 35),
    'cream':        (200, 190, 160),
    'purple':       (220, 100, 255),
    'fire':         (255, 180, 45),
    'ocean':        (70, 180, 255),
    'emerald':      (100, 230, 85),
    'gold':         (255, 200, 60),
    'mono':         (255, 255, 255),
    'copper':       (210, 130, 70),
    'rose':         (200, 90, 160),
    'rust':         (210, 105, 55),
    'lavender':     (180, 120, 220),
    'midnight':     (75, 60, 210),
    'cyan':         (11, 187, 208),
}

# Per-variant groove + track-mark appearance — (groove_rgba, track_rgba).
# Dark body → light groove (highlight), light body → dark groove (shadow).
# Track alpha is roughly 2× groove alpha so boundaries are visible but not huge.
# Tune these to taste per vinyl style.
VINYL_GROOVE_COLORS = {
    # Light bodies — dark shadow haze (subtle)
    'cream':      ((0, 0, 0, 7),        (0, 0, 0, 28)),
    'mono':       ((0, 0, 0, 4),        (0, 0, 0, 28)),
    'fire':       ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'gold':       ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'ocean':      ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'emerald':    ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'lavender':   ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'purple':     ((0, 0, 0, 10),       (0, 0, 0, 40)),
    'rose':       ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'copper':     ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'rust':       ((0, 0, 0, 10),       (0, 0, 0, 40)),
    'cyan':       ((0, 0, 0, 9),        (0, 0, 0, 36)),
    # Dark bodies — light additive shine
    'red':        ((255, 255, 255, 35), (255, 255, 255, 45)),
    'navy':       ((255, 255, 255, 35), (255, 255, 255, 45)),
    'forest':     ((255, 255, 255, 35), (255, 255, 255, 45)),
    'plum':       ((255, 255, 255, 35), (255, 255, 255, 45)),
    'chocolate':  ((255, 255, 255, 35), (255, 255, 255, 45)),
    'slate':      ((255, 255, 255, 25), (255, 255, 255, 36)),
    'amber':      ((255, 255, 255, 35), (255, 255, 255, 45)),
    'teal':       ((255, 255, 255, 35), (255, 255, 255, 45)),
    'burgundy':   ((255, 255, 255, 35), (255, 255, 255, 45)),
    'olive':      ((255, 255, 255, 35), (255, 255, 255, 45)),
    'midnight':   ((255, 255, 255, 35), (255, 255, 255, 45)),
}

# Plain black vinyl: light grooves (light catching the spiral) on a dark body.
BLACK_GROOVE_COLORS = ((90, 90, 90, 80), (110, 110, 110, 130))

# Transparent / clear vinyl.
CLEAR_GROOVE_COLORS = ((255, 255, 255, 55), (255, 255, 255, 90))

# Picture disc (uses album art as the entire face).
PICTURE_GROOVE_COLORS = ((0, 0, 0, 12), (0, 0, 0, 26))

# Mandelbrot color schemes: (interior, r_params, g_params, b_params, groove, track_mark)
# Each channel: (base, amplitude, frequency, phase)
MANDELBROT_COLORS = {
    'purple':    ((15, 5, 30),   (40, 180, 12.0, 0.0), (20, 80, 8.0, 2.0), (80, 175, 10.0, 4.0),    (30, 20, 60),  (50, 35, 85)),
    'fire':      ((30, 5, 0),    (80, 175, 10.0, 0.0), (20, 160, 8.0, 1.5), (5, 40, 6.0, 3.0),      (50, 25, 10),  (70, 40, 20)),
    'ocean':     ((5, 10, 30),   (10, 60, 6.0, 1.0),  (40, 140, 8.0, 0.5), (60, 195, 10.0, 0.0),    (15, 30, 55),  (25, 45, 75)),
    'emerald':   ((5, 20, 10),   (20, 80, 8.0, 2.0),  (50, 180, 10.0, 0.0), (15, 70, 6.0, 1.5),     (15, 40, 20),  (25, 60, 35)),
    'gold':      ((25, 15, 5),   (80, 175, 10.0, 0.0), (50, 150, 9.0, 0.5), (10, 50, 6.0, 2.0),     (50, 40, 15),  (70, 55, 25)),
    'mono':      ((10, 10, 10),  (30, 225, 10.0, 0.0), (30, 225, 10.0, 0.0), (30, 225, 10.0, 0.0),   (35, 35, 35),  (55, 55, 55)),
    'copper':    ((25, 12, 5),   (60, 150, 9.0, 0.5),  (30, 100, 7.0, 1.0), (10, 60, 5.0, 2.5),     (45, 30, 15),  (65, 45, 25)),
    'teal':      ((5, 15, 20),   (10, 50, 6.0, 1.5),  (40, 150, 9.0, 0.0), (50, 160, 8.0, 0.5),     (15, 35, 45),  (25, 50, 60)),
    'rose':      ((25, 8, 15),   (60, 140, 8.0, 0.0),  (20, 70, 6.0, 2.0), (40, 120, 9.0, 1.0),     (45, 25, 35),  (65, 40, 50)),
    'rust':      ((30, 8, 5),    (70, 140, 8.0, 0.0),  (25, 80, 6.0, 1.0), (10, 45, 5.0, 2.5),      (50, 25, 15),  (70, 40, 25)),
    'lavender':  ((18, 10, 25),  (50, 130, 10.0, 1.0), (30, 90, 7.0, 2.5), (60, 160, 9.0, 0.0),     (35, 25, 50),  (50, 35, 70)),
    'midnight':  ((5, 5, 20),    (15, 60, 7.0, 2.0),  (10, 50, 6.0, 1.0), (40, 170, 10.0, 0.0),     (15, 15, 40),  (25, 25, 55)),
}

# Per-mandelbrot-color-scheme groove + track. Keyed on the color name.
MANDELBROT_GROOVE_COLORS = {
    'purple':    ((0, 0, 0, 32), (0, 0, 0, 60)),
    'fire':      ((0, 0, 0, 32), (0, 0, 0, 60)),
    'ocean':     ((0, 0, 0, 32), (0, 0, 0, 60)),
    'emerald':   ((0, 0, 0, 32), (0, 0, 0, 60)),
    'gold':      ((0, 0, 0, 32), (0, 0, 0, 60)),
    'mono':      ((0, 0, 0, 32), (0, 0, 0, 60)),
    'copper':    ((0, 0, 0, 32), (0, 0, 0, 60)),
    'teal':      ((0, 0, 0, 32), (0, 0, 0, 60)),
    'rose':      ((0, 0, 0, 32), (0, 0, 0, 60)),
    'rust':      ((0, 0, 0, 32), (0, 0, 0, 60)),
    'lavender':  ((0, 0, 0, 32), (0, 0, 0, 60)),
    'midnight':  ((255, 255, 255, 22), (255, 255, 255, 45)),
}

# Mandelbrot zoom locations: (cx, cy, zoom, max_iter, name)
MANDELBROT_ZOOMS = [
    (-0.7463,  0.1102,   80.0,  200, 'seahorse'),
    (-0.7453,  0.1127,  600.0,  350, 'seahorse-deep'),
    (-0.1611,  1.0378,  120.0,  250, 'elephant'),
    (-0.7436,  0.1319,  200.0,  300, 'spiral'),
    ( 0.2501,  0.0000,  150.0,  280, 'needle'),
    (-0.5621,  0.6427,  250.0,  300, 'filament'),
    (-0.74364388703, 0.13182590421, 5000.0, 500, 'spiral-center'),
]

# All zoom+color combos: (cx, cy, zoom, max_iter, name, color_scheme)
MANDELBROT_VARIANTS = [
    (*zoom, color)
    for zoom in MANDELBROT_ZOOMS
    for color in MANDELBROT_COLORS
]

# Munafo deep-zoom variants: (config_name, style_id, display_label). Each
# entry maps to a locked config in ../munafo_work/configs/ whose PNG
# snapshot is the source of truth — the renderer downsamples that snapshot
# rather than re-running the perturbation engine (which takes minutes/GPU).
MUNAFO_VARIANTS = [
    ('deep5_v1', 'munafo-deep5', 'Pastel Coral'),     # peach + cyan + lime
    ('deep6_v1', 'munafo-deep6', 'Rainbow Atoll'),    # rainbow rings, period-101
    ('deep7_v1', 'munafo-deep7', 'Magenta Flower'),   # coral + magenta + teal
]

# Per-munafo-variant groove + track-mark colors. Keyed on config name.
# Tuned to each palette's dominant field — dark grooves (normal alpha) on
# light fields read as shadow; light grooves (additive) on dark fields read
# as shine. Brightness >128 in the color triggers additive blending in
# _build_grooves_overlay.
MUNAFO_GROOVE_COLORS = {
    'deep5_v1': ((0, 0, 0, 32), (0, 0, 0, 60)),   # peach field — dark grooves
    'deep6_v1': ((0, 0, 0, 30), (0, 0, 0, 56)),   # bright yellow outer — dark
    'deep7_v1': ((0, 0, 0, 28), (0, 0, 0, 52)),   # magenta/coral mid — dark
}

# Style weights
STYLE_DISTRIBUTION = [
    ('black', 15),
    ('color', 12),
    ('mandelbrot', 22),
    ('nebula', 22),
    ('munafo', 10),
    ('pattern', 8),    # picture-disc with a fractal as the full disc body
    ('clear', 6),
    ('picture', 5),
]


CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache', 'mandelbrot')
NEBULA_CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache', 'nebula')
JULIA_CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache', 'julia')
MUNAFO_CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache', 'munafo')
# The 9000×9000 gold archives live in the sibling `bongsweat` repo. This
# path is only used by prerender_all() to regenerate the vinyl cache; at
# runtime, lp reads from MUNAFO_CACHE_DIR (committed in this repo).
MUNAFO_SOURCE_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                                  'bongsweat', 'configs')

# Julia label variants: (c_real, c_imag, zoom, max_iter, name)
# Used as record labels (rendered into the center disc). Rainbow sinusoidal palette.
JULIA_VARIANTS = [
    (-0.74543,  0.11301, 1.35, 200, 'dendrite'),
    (-0.7269,   0.1889,  1.35, 200, 'rabbit'),
    (-0.8,      0.156,   1.35, 200, 'seahorse'),
]

# Pre-render resolution (radius) — large enough to scale down for any display.
# Sized to cover a typical 1080p display at RECORD_SUPERSAMPLE=4 with minimal upscale.
PRERENDER_SIZE = 800

# Supersample factor for the record body. SS=2 plays nice with the GPU's
# 4-tap bilinear filter (2:1 downscale is well-handled). The grooves overlay
# is built separately at SS=1 (display resolution) to avoid moiré entirely.
RECORD_SUPERSAMPLE = 2


# --- Nebula noise helpers ---

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


# --- Nebula palette functions ---
# Each takes (brightness, blend, t1, t2, t3, hue_shift) and returns (r, g, b)

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

# Per-nebula-variant groove + track. Keyed on the variant name.
NEBULA_GROOVE_COLORS = {
    'purple-fire':    ((0, 0, 0, 30), (0, 0, 0, 56)),
    'ocean-emerald':  ((0, 0, 0, 30), (0, 0, 0, 56)),
    'crimson-gold':   ((0, 0, 0, 30), (0, 0, 0, 56)),
    'electric':       ((0, 0, 0, 30), (0, 0, 0, 56)),
    'emerald-purple': ((0, 0, 0, 30), (0, 0, 0, 56)),
    'deep-emerald':   ((0, 0, 0, 28), (0, 0, 0, 52)),
    'cream-green':    ((0, 0, 0, 22), (0, 0, 0, 44)),
    'bone':           ((0, 0, 0, 18), (0, 0, 0, 36)),
    'cream-rose':     ((0, 0, 0, 22), (0, 0, 0, 44)),
    'diamond-morning':((0, 0, 0, 16), (0, 0, 0, 32)),
    'sunset-peach':   ((0, 0, 0, 16), (0, 0, 0, 32)),
    'lavender-dusk':  ((0, 0, 0, 16), (0, 0, 0, 32)),
    'mint-sky':       ((0, 0, 0, 16), (0, 0, 0, 32)),
    'rose-gold':      ((0, 0, 0, 16), (0, 0, 0, 32)),
    'storm-grey':     ((0, 0, 0, 18), (0, 0, 0, 36)),
    'cotton-candy':   ((0, 0, 0, 16), (0, 0, 0, 32)),
    'butter-cream':   ((0, 0, 0, 16), (0, 0, 0, 32)),
    'seafoam':        ((0, 0, 0, 16), (0, 0, 0, 32)),
    'ember-dusk':     ((0, 0, 0, 16), (0, 0, 0, 32)),
    'plum-wine':      ((0, 0, 0, 16), (0, 0, 0, 32)),
    'arctic':         ((0, 0, 0, 16), (0, 0, 0, 32)),
    'marble':         ((0, 0, 0, 22), (0, 0, 0, 44)),
    'galaxy':         ((255, 255, 255, 22), (255, 255, 255, 45)),
    'galaxy-warm':    ((0, 0, 0, 30), (0, 0, 0, 56)),
    'galaxy-cold':    ((255, 255, 255, 22), (255, 255, 255, 45)),
    'oil-spill':      ((0, 0, 0, 30), (0, 0, 0, 56)),
    'absinthe':       ((0, 0, 0, 30), (0, 0, 0, 56)),
    'coral-reef':     ((0, 0, 0, 30), (0, 0, 0, 56)),
    'bruise':         ((255, 255, 255, 22), (255, 255, 255, 45)),
    'molten':         ((0, 0, 0, 30), (0, 0, 0, 56)),
    'lava-lamp':      ((0, 0, 0, 30), (0, 0, 0, 56)),
}


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


class Display:
    def __init__(self, config, player, port=8000):
        self.player = player
        self.port = port
        self.config = config.get('display', {})
        self.fullscreen = self.config.get('fullscreen', False)
        self.width = self.config.get('width', 1280)
        self.height = self.config.get('height', 720)
        self.url = self.config.get('url', 'https://lp.example.com')

        self._dirty = True
        self._art_path = None
        self._art_texture = None
        self._status_cache = None
        self._record_angle = 0.0
        self._label_art = None
        self._label_art_path = None
        self._current_vinyl_style = None
        self._current_album_path = None
        self._record_texture = None
        self._record_texture_key = None
        self._grooves_texture = None
        self._grooves_texture_key = None
        self._shine_texture = None
        self._shine_texture_key = None
        self._text_cache = {}
        self._needle_tex = None

        self.window = None
        self.renderer = None

        # Screenshot plumbing — request_screenshot() (called from API thread)
        # sets the event; the pygame loop captures the next frame and stores
        # PNG bytes for the requester to read.
        self._screenshot_event = threading.Event()
        self._screenshot_lock = threading.Lock()
        self._screenshot_data = None
        self._record_rect = None  # last-rendered record bounds, for screenshot blur

        player.on('play_start', self._mark_dirty)
        player.on('track_change', self._mark_dirty)
        player.on('album_end', self._mark_dirty)
        player.on('stop', self._mark_dirty)

    def _mark_dirty(self):
        self._dirty = True

    def request_screenshot(self, timeout=8.0):
        """Capture the current frame as PNG bytes. Thread-safe; intended to be
        called from the API thread. Returns bytes on success, None on timeout."""
        print(f'[share] request_screenshot called', flush=True)
        with self._screenshot_lock:
            self._screenshot_data = None
        self._dirty = True  # force a re-render so we capture the latest state
        self._screenshot_event.set()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._screenshot_lock:
                if self._screenshot_data is not None:
                    n = len(self._screenshot_data)
                    print(f'[share] request_screenshot got {n} bytes', flush=True)
                    return self._screenshot_data or None
            time.sleep(0.05)
        print(f'[share] request_screenshot TIMED OUT', flush=True)
        return None

    def _capture_screenshot_if_requested(self):
        """Called from the pygame loop, right after present()."""
        if not self._screenshot_event.is_set():
            return
        print(f'[share] _capture_screenshot_if_requested firing', flush=True)
        self._screenshot_event.clear()
        try:
            surf = self.renderer.to_surface()
            print(f'[share] to_surface size={surf.get_size()}', flush=True)
            # Normalize to the logical render resolution: when the window isn't
            # 16:9 the output is letterboxed, so crop to the centered render area
            # (matching SDL's logical-size scaling) before using logical-space
            # coords like _record_rect.
            ow, oh = surf.get_size()
            if (ow, oh) != (self.width, self.height):
                s = min(ow / self.width, oh / self.height)
                vw, vh = int(self.width * s), int(self.height * s)
                vx, vy = (ow - vw) // 2, (oh - vh) // 2
                surf = surf.subsurface(pygame.Rect(vx, vy, vw, vh)).copy()
                surf = pygame.transform.smoothscale(surf, (self.width, self.height))
                print(f'[share] de-letterboxed to {surf.get_size()}', flush=True)
            if self._record_rect is not None:
                rect = pygame.Rect(self._record_rect).clip(surf.get_rect())
                print(f'[share] record_rect={self._record_rect}, clipped={rect}', flush=True)
                if rect.width > 0 and rect.height > 0:
                    sub = surf.subsurface(rect).copy()
                    print(f'[share] subsurface ok, size={sub.get_size()}', flush=True)
                    if hasattr(pygame.transform, 'gaussian_blur'):
                        sub = pygame.transform.gaussian_blur(sub, 1)
                        print(f'[share] gaussian_blur ok', flush=True)
                    else:
                        sw, sh = sub.get_size()
                        small = pygame.transform.smoothscale(sub, (sw * 3 // 4, sh * 3 // 4))
                        sub = pygame.transform.smoothscale(small, (sw, sh))
                        print(f'[share] smoothscale-blur ok', flush=True)
                    surf.blit(sub, rect.topleft)
                    print(f'[share] blit back ok', flush=True)
            else:
                print(f'[share] no record_rect set', flush=True)
            # Downscale (or scale-to-fit) 1920×1080. PNG encoding stays small
            # enough and the saved image matches typical TV/display output.
            target_w, target_h = 1920, 1080
            if surf.get_size() != (target_w, target_h):
                surf = pygame.transform.smoothscale(surf, (target_w, target_h))
                print(f'[share] scaled to {target_w}x{target_h}', flush=True)
            buf = io.BytesIO()
            pygame.image.save(surf, buf, 'PNG')
            data = buf.getvalue()
            print(f'[share] PNG encoded: {len(data)} bytes', flush=True)
        except Exception as e:
            import traceback
            print(f'[share] EXCEPTION: {type(e).__name__}: {e}', flush=True)
            traceback.print_exc()
            data = b''
        with self._screenshot_lock:
            self._screenshot_data = data

    def run(self):
        # Tell SDL to use linear filtering when sampling textures. Without this,
        # SDL defaults to nearest-neighbor and the supersampled record texture
        # rotates with stair-stepped edges. Must be set before Renderer is created.
        os.environ.setdefault('SDL_HINT_RENDER_SCALE_QUALITY', '2')

        pygame.init()
        pygame.mixer.quit()  # Release audio device for VLC

        # self.width/height are the FIXED internal render resolution; all layout
        # math lives in that space. The window may be any size or fullscreen — the
        # renderer's logical size scales the render to fit, letterboxing to keep
        # aspect, so the look is identical at every window size.
        self.window = sdl2_video.Window('lp', size=(self.width, self.height))
        self.window.resizable = True
        if self.fullscreen:
            self.window.set_fullscreen(desktop=True)

        try:
            self.renderer = sdl2_video.Renderer(self.window, accelerated=1, vsync=True)
            print(f'display: GPU renderer, render res {self.width}x{self.height} (SS={RECORD_SUPERSAMPLE})', flush=True)
        except pygame.error as e:
            print(f'WARN: GPU renderer unavailable ({e}); falling back to software', flush=True)
            self.renderer = sdl2_video.Renderer(self.window, accelerated=0)

        self.renderer.logical_size = (self.width, self.height)

        # Window events that change the output size (or expose a stale frame) —
        # re-assert logical size and force a redraw, since we only present on dirty.
        resize_events = {getattr(pygame, n) for n in
                         ('WINDOWRESIZED', 'WINDOWSIZECHANGED', 'WINDOWEXPOSED',
                          'WINDOWMAXIMIZED', 'WINDOWRESTORED', 'VIDEORESIZE')
                         if hasattr(pygame, n)}

        self.clock = pygame.time.Clock()

        self._load_fonts()
        self._build_needle_texture()
        self._poll_counter = 0

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        running = False
                    elif event.key == pygame.K_ESCAPE:
                        # Esc leaves fullscreen if in it, otherwise quits.
                        if self.fullscreen:
                            self._toggle_fullscreen()
                        else:
                            running = False
                    elif event.key in (pygame.K_f, pygame.K_F11):
                        self._toggle_fullscreen()
                elif event.type in resize_events:
                    self.renderer.logical_size = (self.width, self.height)
                    self._dirty = True

            self._poll_counter += 1
            if self._poll_counter >= 15:
                self._poll_counter = 0
                new_status = self.player.get_status()
                if new_status != self._status_cache:
                    self._status_cache = new_status
                    self._dirty = True

            playing = self._status_cache and self._status_cache.get('playing')

            if playing:
                self._record_angle = (self._record_angle + 0.8) % 360
                self._dirty = True

            if self._dirty:
                self._dirty = False
                self._render()
                self.renderer.present()
                self._capture_screenshot_if_requested()

            self.clock.tick(30)

        pygame.quit()

    def _toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.window.set_fullscreen(desktop=True)
        else:
            self.window.set_windowed()
        # New output size → recompute the letterbox scale, then redraw.
        self.renderer.logical_size = (self.width, self.height)
        self._dirty = True

    def _load_fonts(self):
        self._font_large = pygame.font.SysFont('sans', int(self.height * 0.03))
        self._font_medium = pygame.font.SysFont('sans', int(self.height * 0.026))
        self._font_small = pygame.font.SysFont('sans', int(self.height * 0.02))
        self._font_idle = pygame.font.SysFont('sans', int(self.height * 0.12))

    def _text_tex(self, key, font, text, color):
        """Get a cached text Texture; re-render only when content/color changes."""
        cached = self._text_cache.get(key)
        if cached and cached[0] == text and cached[1] == color:
            return cached[2], cached[3]
        surf = font.render(text, True, color)
        tex = sdl2_video.Texture.from_surface(self.renderer, surf)
        rect = surf.get_rect()
        self._text_cache[key] = (text, color, tex, rect)
        return tex, rect

    def _build_needle_texture(self):
        """Pre-build the small needle-tip circle as a Texture (drawn each frame)."""
        s = pygame.Surface((9, 9), pygame.SRCALPHA)
        pygame.draw.circle(s, NEEDLE_COLOR, (4, 4), 3)
        self._needle_tex = sdl2_video.Texture.from_surface(self.renderer, s)

    def _get_circular_art(self, art_path, radius):
        """Get album art masked into a circle at the given radius."""
        try:
            img = pygame.image.load(art_path)
            d = radius * 2
            # Force RGBA so BLEND_RGBA_MULT actually masks alpha (JPEG loads as RGB).
            rgba = pygame.Surface((d, d), pygame.SRCALPHA)
            scaled = pygame.transform.smoothscale(img, (d, d))
            rgba.blit(scaled, (0, 0))
            circle_mask = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(circle_mask, (255, 255, 255, 255), (radius, radius), radius)
            rgba.blit(circle_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            return rgba
        except Exception:
            return None

    def _get_label_art(self, art_path, label_r):
        """Get circular album art for the record label, cached by path."""
        if art_path == self._label_art_path and self._label_art is not None:
            if self._label_art.get_width() == label_r * 2:
                return self._label_art
        self._label_art_path = art_path
        self._label_art = self._get_circular_art(art_path, label_r)
        return self._label_art

    def _get_julia_label(self, name, label_r):
        """Load a pre-rendered Julia disc and scale to the label radius.
        Cached on the Display instance by (name, label_r)."""
        key = (name, label_r)
        cached = getattr(self, '_julia_label_cache', {})
        if key in cached:
            return cached[key]
        path = os.path.join(JULIA_CACHE_DIR, f'{name}.png')
        if not os.path.isfile(path):
            return None
        try:
            img = pygame.image.load(path)
        except Exception:
            return None
        d = label_r * 2
        scaled = pygame.transform.smoothscale(img, (d, d))
        # Ensure RGBA so alpha is preserved on later blits.
        target = pygame.Surface((d, d), pygame.SRCALPHA)
        target.blit(scaled, (0, 0))
        cached[key] = target
        self._julia_label_cache = cached
        return target

    def _get_pattern_label(self, label_setting, label_r):
        """Render a fractal cache (mandelbrot / nebula / munafo) as a label.
        `label_setting` is like 'mandelbrot-seahorse-purple', 'nebula-galaxy',
        or 'munafo-deep5_v1'. Returns a circular RGBA surface or None."""
        key = (label_setting, label_r)
        cached = getattr(self, '_pattern_label_cache', {})
        if key in cached:
            return cached[key]

        if label_setting.startswith('mandelbrot-'):
            path = os.path.join(CACHE_DIR, f'{label_setting[len("mandelbrot-"):]}.png')
        elif label_setting.startswith('nebula-'):
            path = os.path.join(NEBULA_CACHE_DIR, f'{label_setting[len("nebula-"):]}.png')
        elif label_setting.startswith('munafo-'):
            path = os.path.join(MUNAFO_CACHE_DIR, f'{label_setting[len("munafo-"):]}.png')
        else:
            return None

        if not os.path.isfile(path):
            return None
        try:
            img = pygame.image.load(path)
        except Exception:
            return None
        d = label_r * 2
        scaled = pygame.transform.smoothscale(img, (d, d))
        # Re-mask to the label radius — source PNGs are masked to the full
        # vinyl disc, which is larger than the label.
        target = pygame.Surface((d, d), pygame.SRCALPHA)
        target.blit(scaled, (0, 0))
        mask = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (label_r, label_r), label_r)
        target.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        cached[key] = target
        self._pattern_label_cache = cached
        return target

    @staticmethod
    def _draw_fake_label_text(surf, cx, cy, label_r, accent_c):
        """Draw chickenscratch fake text on a colored record label."""
        rng = random.Random(42)
        d = label_r * 2
        tmp = pygame.Surface((d, d), pygame.SRCALPHA)
        lx, ly = label_r, label_r

        text_col = (*accent_c[:3], 140)
        bold_col = (*accent_c[:3], 180)
        ring_col = (*accent_c[:3], 50)

        # Decorative rings like a real label
        pygame.draw.circle(tmp, ring_col, (lx, ly), int(label_r * 0.88), 1)
        pygame.draw.circle(tmp, ring_col, (lx, ly), int(label_r * 0.55), 1)

        # "Title" line — slightly thicker dashes
        ty = ly - int(label_r * 0.28)
        hw = int(label_r * 0.45)
        x = lx - hw
        while x < lx + hw:
            w = rng.randint(max(2, label_r // 10), max(4, label_r // 4))
            ex = min(x + w, lx + hw)
            pygame.draw.line(tmp, bold_col, (x, ty), (ex, ty), 2)
            x = ex + rng.randint(2, max(3, label_r // 12))

        # Smaller text lines
        for yo in [-0.08, 0.08, 0.22, 0.38]:
            y = ly + int(yo * label_r)
            da = abs(yo) + 0.15
            lhw = int(math.sqrt(max(0, 1 - da * da)) * label_r * 0.45)
            x = lx - lhw
            while x < lx + lhw:
                w = rng.randint(max(2, label_r // 15), max(3, label_r // 6))
                ex = min(x + w, lx + lhw)
                pygame.draw.line(tmp, text_col, (x, y), (ex, y), 1)
                x = ex + rng.randint(1, max(2, label_r // 10))

        surf.blit(tmp, (cx - label_r, cy - label_r))

    @staticmethod
    def _draw_label_decor(surf, cx, cy, label_r, slots, seed=0, vertical=False):
        """Place monochrome critter silhouettes in the label's empty spaces — one
        per slot. `vertical` puts them top/bottom (for centered straight/blocky
        text); otherwise left/right (for curved top/bottom text). `slots` is up
        to two (name, rgb) pairs; name may be a critter, 'random', or 'none'."""
        path = pygame.font.match_font('notoemoji')   # monochrome outline glyphs
        if not path:
            return
        font = pygame.font.Font(path, 96)
        target = max(8, int(label_r * 0.42))
        if vertical:
            off = int(label_r * 0.62)
            positions = [(cx, cy - off), (cx, cy + off)]   # 12 and 6 o'clock
        else:
            off = int(label_r * 0.5)
            positions = [(cx - off, cy), (cx + off, cy)]   # 9 and 3 o'clock
        rng = random.Random(seed)
        for (name, col), (sx, sy) in zip(slots, positions):
            if not name or name == 'none':
                continue
            if name == 'random':
                name = rng.choice(list(DECOR_EMOJI))
            if name not in DECOR_EMOJI:
                continue
            try:
                g = font.render(DECOR_EMOJI[name], True, tuple(col[:3]))
            except Exception:
                continue
            g = pygame.transform.smoothscale(g, (target, target))
            surf.blit(g, g.get_rect(center=(sx, sy)))

    @staticmethod
    def _draw_arc_text(surf, cx, cy, radius, text, font, color, top=True):
        """Blit `text` curved along a circle arc, centered at top or bottom."""
        if not text:
            return
        glyphs = [(ch, font.render(ch, True, color)) for ch in text]
        widths = [g.get_width() for _, g in glyphs]
        gap = max(1, int(font.get_height() * 0.06))
        total_w = sum(widths) + gap * (len(text) - 1)
        total_ang = total_w / float(radius)
        if top:
            a = -math.pi / 2 - total_ang / 2.0   # start left of top center
            step = 1.0
        else:
            a = math.pi / 2 + total_ang / 2.0     # start left of bottom center
            step = -1.0
        for (ch, g), w in zip(glyphs, widths):
            char_ang = w / float(radius)
            ca = a + step * char_ang / 2.0
            px = cx + radius * math.cos(ca)
            py = cy + radius * math.sin(ca)
            deg = -(math.degrees(ca) + 90) if top else -(math.degrees(ca) - 90)
            rot = pygame.transform.rotate(g, deg)
            surf.blit(rot, rot.get_rect(center=(int(px), int(py))))
            a += step * (char_ang + gap / float(radius))

    @staticmethod
    def _draw_label_text(surf, cx, cy, label_r, accent_c, artist=None, album=None,
                         mode='curved', font_name='serif',
                         artist_color=None, album_color=None):
        """Real artist/album text on a colored label.

        mode: 'none'     — no text at all (blank label)
              'curved'   — artist on the top arc, album on the bottom arc
              'straight'  — centered horizontal lines
              'blocky'    — centered, heavy/condensed block lettering
        Falls back to abstract chickenscratch when there's no metadata.
        """
        if mode == 'none':
            return
        if not artist and not album:
            Display._draw_fake_label_text(surf, cx, cy, label_r, accent_c)
            return
        d = label_r * 2
        tmp = pygame.Surface((d, d), pygame.SRCALPHA)
        lx, ly = label_r, label_r
        ring_col = (*accent_c[:3], 60)
        a_col = (*(artist_color or accent_c[:3]), 235)
        b_col = (*(album_color or accent_c[:3]), 235)
        pygame.font.init()

        if mode == 'curved':
            pygame.draw.circle(tmp, ring_col, (lx, ly), int(label_r * 0.92), 1)
            font = pygame.font.SysFont(font_name, max(8, int(label_r * 0.15)), bold=True)
            text_r = int(label_r * 0.74)
            if artist:
                Display._draw_arc_text(tmp, lx, ly, text_r, artist.upper(), font, a_col, top=True)
            if album:
                Display._draw_arc_text(tmp, lx, ly, text_r, album.upper(), font, b_col, top=False)
        else:
            blocky = mode == 'blocky'
            fs = int(label_r * (0.22 if blocky else 0.17))
            font = pygame.font.SysFont(font_name, max(8, fs), bold=True)
            lines = [(t.upper(), c) for t, c in ((artist, a_col), (album, b_col)) if t]
            rendered = []
            maxw = int(label_r * 1.45)
            for ln, c in lines:
                g = font.render(ln, True, c)
                if g.get_width() > maxw:   # shrink long names proportionally (no squish)
                    sc = maxw / g.get_width()
                    g = pygame.transform.smoothscale(
                        g, (maxw, max(1, int(g.get_height() * sc))))
                rendered.append(g)
            gap = int(label_r * (0.20 if blocky else 0.16))   # roomy artist↔album gap
            total_h = sum(g.get_height() for g in rendered) + gap * (len(rendered) - 1)
            y = ly - total_h // 2
            for g in rendered:
                tmp.blit(g, g.get_rect(midtop=(lx, y)))
                y += g.get_height() + gap

        surf.blit(tmp, (cx - label_r, cy - label_r))

    def _get_vinyl_style(self, album_path):
        """Get or compute vinyl style for current album."""
        override = self.player.vinyl_style
        cache_key = (album_path, override)
        if cache_key != (self._current_album_path, getattr(self, '_current_override', None)):
            self._current_album_path = album_path
            self._current_override = override
            self._current_vinyl_style = _pick_vinyl_style(album_path, override) if album_path else None
        return self._current_vinyl_style

    def _build_record(self, size, boundaries, album_dur, art_path=None, album_path=None,
                      artist=None, album=None):
        """Build the vinyl record body (no grooves/track marks — those go on the overlay)."""
        d = size * 2
        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        center = (size, size)

        style = self._get_vinyl_style(album_path)
        if not style:
            style = {'type': 'black'}

        style_type = style['type']

        if style_type == 'picture' and art_path:
            pic = self._get_circular_art(art_path, size)
            if pic:
                surf.blit(pic, (0, 0))
            else:
                self._draw_black_vinyl(surf, size, center)
        elif style_type == 'clear':
            self._draw_clear_vinyl(surf, size, center)
        elif style_type == 'color':
            base = VINYL_COLORS.get(style.get('color'), VINYL_BLACK[0])
            self._draw_color_vinyl(surf, size, center, base)
        elif style_type == 'mandelbrot':
            variant = style['variant']
            self._draw_mandelbrot_vinyl(surf, size, center, variant)
        elif style_type == 'nebula':
            variant = style['variant']
            self._draw_nebula_vinyl(surf, size, center, variant)
        elif style_type == 'munafo':
            variant = style['variant']
            self._draw_munafo_vinyl(surf, size, center, variant)
        elif style_type == 'pattern':
            # Pattern picture-disc: fractal as the full disc body, no label.
            sub = style.get('sub') or {}
            sub_type = sub.get('type')
            if sub_type == 'mandelbrot':
                self._draw_mandelbrot_vinyl(surf, size, center, sub['variant'])
            elif sub_type == 'nebula':
                self._draw_nebula_vinyl(surf, size, center, sub['variant'])
            elif sub_type == 'munafo':
                self._draw_munafo_vinyl(surf, size, center, sub['variant'])
            else:
                self._draw_black_vinyl(surf, size, center)
        else:
            self._draw_black_vinyl(surf, size, center)

        # Label — album art, colored, fractal, or fallback. Skip entirely
        # for picture-disc styles ('picture' = album art disc, 'pattern' =
        # fractal disc) since those use the body all the way through.
        if style_type not in ('picture', 'pattern'):
            label_r = int(size * LABEL_RADIUS)
            label_setting = self.player.vinyl_label
            text_mode = self.player.vinyl_label_text
            text_font = self.player.vinyl_label_font

            # Text + decorations render over EVERY label type except the
            # full-disc picture/pattern styles (handled by the outer guard).
            # Solid labels get an accent derived from their color; image labels
            # (album art / fractal / julia) get a light default for 'auto'.
            IMG_ACCENT = (245, 245, 245)
            is_image = False

            if label_setting == 'art':
                label_art = self._get_label_art(art_path, label_r) if art_path else None
                if label_art:
                    surf.blit(label_art, (size - label_r, size - label_r))
                    label_accent, is_image = IMG_ACCENT, True
                else:
                    pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                    label_accent = VINYL_LABEL_DARK
            elif label_setting.startswith('color-'):
                # Any vinyl color doubles as a label color (unified palette).
                color_name = label_setting[len('color-'):]
                main_c = VINYL_COLORS.get(color_name, VINYL_LABEL)
                label_accent = tuple(int(c * 0.55) for c in main_c)
                pygame.draw.circle(surf, main_c, center, label_r)
            elif label_setting.startswith('label-'):
                # Legacy label-color palette (superseded by color-*).
                color_name = label_setting[len('label-'):]
                main_c, label_accent = LABEL_COLORS.get(color_name, (VINYL_LABEL, VINYL_LABEL_DARK))
                pygame.draw.circle(surf, main_c, center, label_r)
            elif label_setting.startswith('julia-'):
                jl = self._get_julia_label(label_setting[len('julia-'):], label_r)
                if jl:
                    surf.blit(jl, (size - label_r, size - label_r))
                    label_accent, is_image = IMG_ACCENT, True
                else:
                    pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                    label_accent = VINYL_LABEL_DARK
            elif (label_setting.startswith('mandelbrot-')
                  or label_setting.startswith('nebula-')
                  or label_setting.startswith('munafo-')):
                fl = self._get_pattern_label(label_setting, label_r)
                if fl:
                    surf.blit(fl, (size - label_r, size - label_r))
                    label_accent, is_image = IMG_ACCENT, True
                else:
                    pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                    label_accent = VINYL_LABEL_DARK
            else:
                pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                label_accent = VINYL_LABEL_DARK

            p = self.player
            vertical = text_mode in ('straight', 'blocky')
            # Don't scribble fake chickenscratch over an image label; real text
            # (when there's metadata) and decorations are fine everywhere.
            if artist or album or not is_image:
                artist_col = _resolve_color(p.vinyl_label_artist_color, label_accent)
                album_col = _resolve_color(p.vinyl_label_album_color, label_accent)
                self._draw_label_text(surf, size, size, label_r, label_accent,
                                      artist, album, text_mode, text_font,
                                      artist_col, album_col)
            d1, d2 = p.vinyl_label_decor1, p.vinyl_label_decor2
            if (d1 and d1 != 'none') or (d2 and d2 != 'none'):
                slots = [
                    (d1, _resolve_color(p.vinyl_label_decor1_color, label_accent)),
                    (d2, _resolve_color(p.vinyl_label_decor2_color, label_accent)),
                ]
                seed = abs(hash(album_path or '')) % (1 << 30)
                self._draw_label_decor(surf, size, size, label_r, slots, seed, vertical)

        # Spindle hole
        pygame.draw.circle(surf, DARK_BG, center, int(size * 0.04))

        # Brightness adjustment
        brightness = self.player.vinyl_brightness
        if brightness < 100:
            alpha = int(255 * (1 - brightness / 100))
            dim = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(dim, (0, 0, 0, alpha), center, size)
            surf.blit(dim, (0, 0))

        return surf

    def _build_grooves_overlay(self, size, style, boundaries, album_dur):
        """Build the music-zone overlay with track-boundary gaps.

        Returns (surface, blend_mode) where blend_mode is 'blend' (normal alpha)
        for a darkening haze on light vinyls, or 'add' for an additive shine on
        patterned and dark vinyls. Shine renders consistently regardless of
        whatever the body texture is underneath — additive light always brightens.
        """
        d = size * 2
        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        center = (size, size)

        if not style:
            style = {'type': 'black'}
        style_type = style.get('type', 'black')

        overlay_c = None
        blend_mode = 'blend'

        if style_type == 'clear':
            # Bright body — additive shine makes grooves read as highlights
            # catching the light, not as washed-out haze.
            overlay_c = CLEAR_GROOVE_COLORS[0]
            blend_mode = 'add'
        elif style_type == 'color':
            overlay_c = VINYL_GROOVE_COLORS.get(
                style.get('color', ''), ((0, 0, 0, 28), None))[0]
            # Dark bodies get a light shine (additive); light bodies get a
            # dark haze (normal alpha blend).
            if overlay_c and overlay_c[0] > 128:  # light overlay color
                blend_mode = 'add'
        elif style_type == 'black':
            # Darker bands in the music zone — grooves cast deeper shadows
            # than the smooth lead-in flats. Normal alpha blend.
            overlay_c = (0, 0, 0, 25)
        elif style_type == 'munafo':
            variant = style.get('variant')
            cfg_name = variant[0] if variant else None
            overlay_c = MUNAFO_GROOVE_COLORS.get(cfg_name, ((0, 0, 0, 30), None))[0]
            blend_mode = 'add' if overlay_c[0] > 128 else 'blend'
        elif style_type == 'pattern':
            # Inherit groove behavior from the underlying fractal type.
            sub = style.get('sub') or {}
            sub_type = sub.get('type')
            if sub_type == 'munafo':
                variant = sub.get('variant')
                cfg_name = variant[0] if variant else None
                overlay_c = MUNAFO_GROOVE_COLORS.get(cfg_name, ((0, 0, 0, 30), None))[0]
                blend_mode = 'add' if overlay_c[0] > 128 else 'blend'
            else:
                overlay_c = (255, 255, 255, 45)
                blend_mode = 'add'
        elif style_type in ('mandelbrot', 'nebula', 'picture'):
            overlay_c = (255, 255, 255, 45)
            blend_mode = 'add'

        if overlay_c is not None:
            self._draw_music_zones(surf, size, center, overlay_c,
                                   boundaries=boundaries, album_dur=album_dur,
                                   gap_half_width=2)

        brightness = self.player.vinyl_brightness
        if brightness < 100:
            arr = pygame.surfarray.pixels_alpha(surf)
            arr[:] = (arr.astype(np.float32) * brightness / 100).astype(np.uint8)
            del arr

        return surf, blend_mode

    # Screen-fixed specular shine. Drawn at a CONSTANT angle on top of the
    # rotating body + grooves, so the room-light reflection stays put while the
    # record spins — light doesn't rotate with the disc. White + additive, so
    # it reads as a highlight over any body color/art/fractal.
    # A narrow specular streak, alpha-blended toward white (NOT additive, so it
    # never blows out a bright body like the clear platter). Fixed in screen
    # space and applied to all styles.
    _SHINE_PARAMS = dict(
        streak_x_frac     = -0.05,
        streak_angle_deg  = 15.0,   # 11:30→5:30 tilt (slight top-left lean)
        streak_core_width = 0.06,   # tight bright core
        streak_core_alpha = 0.28,
        streak_halo_width = 0.16,   # modest soft halo
        streak_halo_alpha = 0.10,
    )
    # Per-style streak overrides for the shared shine overlay. Currently empty —
    # clear vinyl owns its specular streak inside _draw_clear_vinyl so the light
    # rotates with the disc and reads as "from within", and every other style is
    # happy with _SHINE_PARAMS.
    _SHINE_OVERRIDES_BY_TYPE = {}
    # Per-style gloss: vinyl is glossy across the board, but album-art /
    # fractal faces get a lighter touch so detail isn't blown out. Clear is 0
    # because its streak is drawn inside the rotating disc body (see
    # _draw_clear_vinyl), not as a screen-fixed reflection.
    _GLOSS_BY_TYPE = {
        'clear': 0.0, 'color': 0.95, 'black': 0.7,
        'mandelbrot': 0.7, 'nebula': 0.7, 'munafo': 0.7,
        'picture': 0.55, 'pattern': 0.65,
    }

    def _build_shine_overlay(self, size, style):
        """Build the fixed specular shine overlay (white RGBA, additive blend).

        Returns a surface to draw at angle=0 over the spinning record.
        """
        style_type = (style or {}).get('type', 'black')
        p = {**self._SHINE_PARAMS, **self._SHINE_OVERRIDES_BY_TYPE.get(style_type, {})}
        gloss = self._GLOSS_BY_TYPE.get(style_type, 0.7)
        d = size * 2
        cx = cy = size

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        in_disc = np.clip(size - r + 0.5, 0.0, 1.0)

        # Tilted specular streak (window reflection) — broad core + wide halo,
        # full-height column (matches the original clear-vinyl streak).
        ang = np.deg2rad(p['streak_angle_deg'])
        u = (dx - size * p['streak_x_frac']) * np.cos(ang) - dy * np.sin(ang)
        core = np.exp(-(u / (size * p['streak_core_width'])) ** 2) * p['streak_core_alpha']
        halo = np.exp(-(u / (size * p['streak_halo_width'])) ** 2) * p['streak_halo_alpha']
        streak = core + halo

        alpha_frac = np.clip(streak * gloss, 0.0, 1.0) * in_disc

        # Don't shine over the center label — it's paper, not glossy vinyl.
        # Picture / pattern discs have no label (body runs edge-to-edge).
        if (style or {}).get('type', 'black') not in ('picture', 'pattern'):
            label_r = size * LABEL_RADIUS
            outside_label = np.clip(r - label_r + 0.5, 0.0, 1.0)
            alpha_frac = alpha_frac * outside_label

        brightness = self.player.vinyl_brightness
        if brightness < 100:
            alpha_frac = alpha_frac * (brightness / 100.0)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = 255
        rgba[..., 1] = 255
        rgba[..., 2] = 255
        rgba[..., 3] = (alpha_frac * 255.0).astype(np.uint8)

        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0))
        return surf

    @staticmethod
    def _draw_specular_highlight(surf, size, center, color, highlight_angle=-np.pi * 0.35):
        """Render a single angular specular highlight — a soft bright crescent
        on one side of the disc, suggesting overhead light reflection.
        """
        d = size * 2
        cx = d // 2
        cy = d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        theta = np.arctan2(dy, dx)

        # Soft-edged disc mask.
        in_disc = np.clip(size - r + 0.5, 0.0, 1.0)

        # Angular intensity: smooth crescent peaking at highlight_angle.
        phase = np.cos(theta - highlight_angle)
        angular = np.maximum(phase, 0.0) ** 2

        alpha_frac = in_disc * angular

        alpha_val = color[3] if len(color) == 4 else 255
        alpha = (alpha_frac * alpha_val).astype(np.uint8)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = color[0]
        rgba[..., 1] = color[1]
        rgba[..., 2] = color[2]
        rgba[..., 3] = alpha

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    @staticmethod
    def _draw_music_zones(surf, size, center, color, boundaries=None,
                          album_dur=None, gap_half_width=2):
        """Render the music-groove zones as a hazy color overlay with track gaps."""
        d = size * 2
        r_inner = size * INNER_GROOVE
        r_outer = size * OUTER_GROOVE
        cx = d // 2
        cy = d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)

        # Soft-edged annular band (1-px AA falloff at the band's inner/outer edge).
        alpha_frac = np.clip(r - r_inner, 0.0, 1.0) * np.clip(r_outer - r, 0.0, 1.0)

        # Carve gaps at each track boundary with 1-px soft edges.
        if boundaries and album_dur and album_dur > 0:
            groove_range = (OUTER_GROOVE - INNER_GROOVE) * size
            for b in boundaries[1:]:
                frac = b / album_dur
                r_boundary = size * OUTER_GROOVE - frac * groove_range
                gap_factor = np.clip(np.abs(r - r_boundary) - (gap_half_width - 1),
                                     0.0, 1.0)
                alpha_frac = alpha_frac * gap_factor

        alpha_val = color[3] if len(color) == 4 else 255
        alpha = (alpha_frac * alpha_val).astype(np.uint8)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = color[0]
        rgba[..., 1] = color[1]
        rgba[..., 2] = color[2]
        rgba[..., 3] = alpha

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)


    @staticmethod
    def _draw_grooves(surf, size, center, color, spacing=3, ss_factor=None,
                      boundaries=None, album_dur=None, gap_half_width=2):
        """Draw the record's groove as a single continuous spiral, with subpixel AA.

        Real LP grooves are a spiral. Rotation has a visible effect. `spacing`
        is the spiral pitch (radial advance per turn) at display resolution.

        At each track boundary, the spiral is suppressed in a small radial band:
        on a real LP these are flat (musicless) lead-in grooves between tracks,
        which read visually as the boundary marker.
        """
        if ss_factor is None:
            ss_factor = RECORD_SUPERSAMPLE
        d = size * 2
        pitch = spacing * ss_factor
        r_inner = size * INNER_GROOVE
        r_outer = size * OUTER_GROOVE
        cx = d // 2
        cy = d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        theta = np.arctan2(dy, dx)

        in_band = (r >= r_inner) & (r <= r_outer)

        # Radial distance to nearest spiral arm.
        spiral_phase = (2 * np.pi / pitch) * r
        diff = np.mod(theta - spiral_phase, 2 * np.pi)
        mod_phase = np.minimum(diff, 2 * np.pi - diff)
        radial_dist = mod_phase * pitch / (2 * np.pi)

        # 1-display-px stroke = ss_factor surface px.
        half_stroke = ss_factor / 2.0
        alpha_frac = np.clip(half_stroke + 0.5 - radial_dist, 0.0, 1.0)

        # Suppress the spiral inside each track-boundary gap.
        if boundaries and album_dur and album_dur > 0:
            groove_range = (OUTER_GROOVE - INNER_GROOVE) * size
            gap_half = gap_half_width * ss_factor
            for b in boundaries[1:]:
                frac = b / album_dur
                r_boundary = size * OUTER_GROOVE - frac * groove_range
                in_gap = np.abs(r - r_boundary) < gap_half
                alpha_frac = np.where(in_gap, 0.0, alpha_frac)

        alpha_val = color[3] if len(color) == 4 else 255
        alpha = (in_band * alpha_frac * alpha_val).astype(np.uint8)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = color[0]
        rgba[..., 1] = color[1]
        rgba[..., 2] = color[2]
        rgba[..., 3] = alpha

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    def _draw_black_vinyl(self, surf, size, center):
        """Draw a plain black vinyl base disc (grooves go on the overlay)."""
        base, _, _ = VINYL_BLACK
        pygame.draw.circle(surf, base, center, size)

    # Colored-vinyl body. Flat fill reads dull, so we brighten the pigment and
    # add a radial rim vignette for a domed look. Both are rotation-invariant
    # (the directional/specular "shine" is a separate fixed overlay — see
    # _build_shine_overlay — so light doesn't spin with the disc).
    _COLOR_PARAMS = dict(
        lift        = 0.18,   # brighten body toward white (overall pop)
        edge_darken = 0.20,   # vignette at the rim for a domed look
    )

    def _draw_color_vinyl(self, surf, size, center, base, **overrides):
        """Draw a brightened colored-vinyl base disc (radial shading only)."""
        p = {**self._COLOR_PARAMS, **overrides}
        d = size * 2
        cx, cy = d // 2, d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        in_disc = np.clip(size - r + 0.5, 0.0, 1.0)
        rr = np.clip(r / size, 0.0, 1.0)

        base = np.array(base, dtype=np.float32)
        # Brighten the body toward white — lifts dull colors without hue shift
        # and never clips (channels already near 255 barely move).
        body = base + (255.0 - base) * p['lift']

        # Radial vignette only — darken toward the rim for depth.
        shade = 1.0 - p['edge_darken'] * rr ** 3

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = np.clip(body[0] * shade, 0, 255).astype(np.uint8)
        rgba[..., 1] = np.clip(body[1] * shade, 0, 255).astype(np.uint8)
        rgba[..., 2] = np.clip(body[2] * shade, 0, 255).astype(np.uint8)
        rgba[..., 3] = (in_disc * 255.0).astype(np.uint8)

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    # Tunable knobs for the clear-vinyl look. Each parameter is independent
    # so we can dial them one at a time.
    _CLEAR_PARAMS = dict(
        # --- Platter / disc body. We can't lighten the player UI bg, so
        # the disc itself carries the silver/white weight. Near-opaque
        # silver so it reads as "clear vinyl on a light surface" against
        # any background.
        platter_color        = (210, 215, 220),  # silver-white
        platter_alpha        = 0.92,
        body_alpha           = 0.03,
        # --- Specular streak (vertical window-reflection column).
        # SOFT and WIDE — reference shows a broad luminous column, not a
        # hard narrow band.
        streak_x_frac        = -0.05,
        streak_angle_deg     = -4.0,
        streak_core_width    = 0.13,   # broad bright core
        streak_core_alpha    = 0.45,   # lower since base is already bright
        streak_halo_width    = 0.45,   # very wide soft halo
        streak_halo_alpha    = 0.35,
        streak_top_fade      = 0.0,
        # --- Concentric groove striations across the disc face ---
        striation_alpha      = 0.30,
        striation_freq       = 0.45,
        # --- Rainbow refraction (more visible now that platter is bright) ---
        rainbow_strength     = 0.80,
        # --- Rim ---
        rim_alpha            = 0.55,
        rim_width_px         = 2.5,
    )

    def _draw_clear_vinyl(self, surf, size, center, **overrides):
        """Draw a clear-vinyl base disc with platter + shimmer.

        Layers (back-to-front):
          1. Silver platter — gives the disc weight against the dark UI
             background so the clear vinyl reads as "sitting on a
             turntable" rather than "ghost".
          2. Body — slight overall brightness on top of the platter.
          3. Specular streak — bright Gaussian CORE + wider HALO, slightly
             tilted, fading top-to-bottom (light from above). Clear vinyl
             intentionally bakes its streak into the rotating disc body
             (rather than the screen-fixed shine overlay used by every other
             style) — this combined-pass look is what gives it its glow.
          4. Groove shimmer — subtle concentric brighter bands in the
             music zone where light catches groove ridges.
          5. Rim — bright edge highlight.

        Pass keyword overrides to tweak per-call:
            self._draw_clear_vinyl(surf, size, center, streak_core_alpha=0.9)
        """
        p = {**self._CLEAR_PARAMS, **overrides}

        d = size * 2
        cx, cy = d // 2, d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        in_disc = np.clip(size - r + 0.5, 0.0, 1.0)

        # 1+2. Platter (silver base) + faint body on top, as a single layer.
        platter_a = in_disc * p['platter_alpha']
        body_a = in_disc * p['body_alpha']

        pc = np.array(p['platter_color'], dtype=np.float32)

        # 3. Streak (rotated)
        ang = np.deg2rad(p['streak_angle_deg'])
        u = (dx - size * p['streak_x_frac']) * np.cos(ang) - dy * np.sin(ang)
        core_sigma = size * p['streak_core_width']
        halo_sigma = size * p['streak_halo_width']
        core = np.exp(-(u / core_sigma) ** 2) * p['streak_core_alpha']
        halo = np.exp(-(u / halo_sigma) ** 2) * p['streak_halo_alpha']
        vfade = np.clip((size - dy) / (2 * size), 0.0, 1.0) ** p['streak_top_fade']
        streak = (core + halo) * vfade * in_disc

        # 4. Concentric groove striations — visible across the whole disc
        # face (not just the music zone), modulating sinusoidally on r.
        # Strongest in the mid-radius where light has the most surface area
        # to catch, falling off near center and edge.
        radial_env = np.clip(in_disc, 0.0, 1.0) * np.clip(r / size, 0.0, 1.0)
        striations = (0.5 + 0.5 * np.sin(r * p['striation_freq'])) * radial_env * p['striation_alpha']

        # 5. Rim
        rim = np.clip(1.0 - np.abs(r - (size - 1.5)) / p['rim_width_px'],
                      0.0, 1.0) * p['rim_alpha']

        white_a = np.clip(body_a + streak + striations + rim, 0.0, 1.0)

        # --- Rainbow refraction tints ---
        # Where light catches the grooves it doesn't read as pure white —
        # plastic refracts wavelengths slightly differently, giving an
        # iridescent shimmer. We modulate a HSV hue with r and apply it
        # at low saturation, scaled to the striation strength so it only
        # shows where light is actually catching.
        hue = (r * p['striation_freq'] * 0.10) % 1.0
        # HSV → RGB with low saturation. Cheap inline conversion:
        i = (hue * 6.0).astype(np.int32) % 6
        f = hue * 6.0 - (hue * 6.0).astype(np.int32)
        # Saturated rainbow channels (sat=1, val=1).
        rb_r = np.where(i == 0, 1.0,
              np.where(i == 1, 1 - f,
              np.where(i == 2, 0.0,
              np.where(i == 3, 0.0,
              np.where(i == 4, f, 1.0)))))
        rb_g = np.where(i == 0, f,
              np.where(i == 1, 1.0,
              np.where(i == 2, 1.0,
              np.where(i == 3, 1 - f,
              np.where(i == 4, 0.0, 0.0)))))
        rb_b = np.where(i == 0, 0.0,
              np.where(i == 1, 0.0,
              np.where(i == 2, f,
              np.where(i == 3, 1.0,
              np.where(i == 4, 1.0, 1 - f)))))
        # Iridescence weight — only where the striations are catching light.
        irid_w = striations * p['rainbow_strength']
        # Mix the rainbow color into the white-highlight color.
        hi_r = 255.0 * (1 - irid_w) + (rb_r * 255.0) * irid_w
        hi_g = 255.0 * (1 - irid_w) + (rb_g * 255.0) * irid_w
        hi_b = 255.0 * (1 - irid_w) + (rb_b * 255.0) * irid_w

        # Composite — platter base lightened toward (white/iridescent) by
        # the white_a alpha.
        r_arr = pc[0] * (1.0 - white_a) + hi_r * white_a
        g_arr = pc[1] * (1.0 - white_a) + hi_g * white_a
        b_arr = pc[2] * (1.0 - white_a) + hi_b * white_a
        alpha = np.maximum(platter_a, white_a) * 255.0

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = np.clip(r_arr, 0, 255).astype(np.uint8)
        rgba[..., 1] = np.clip(g_arr, 0, 255).astype(np.uint8)
        rgba[..., 2] = np.clip(b_arr, 0, 255).astype(np.uint8)
        rgba[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    def _draw_track_marks(self, surf, size, center, color, boundaries, album_dur, ss_factor=None):
        """Draw track boundary rings at album track positions, with subpixel AA.

        Track marks remain concentric circles (one per track) — they're not part
        of the spiral, they mark where one track ends and the next begins.
        Each ring is 1 display pixel wide.
        """
        if not (album_dur > 0 and boundaries):
            return
        if ss_factor is None:
            ss_factor = RECORD_SUPERSAMPLE

        d = size * 2
        groove_range = (OUTER_GROOVE - INNER_GROOVE) * size
        cx = d // 2
        cy = d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)

        # 2-display-px stroke (visibly heavier than the 1-px spiral, but
        # not "huge"). half_stroke=0.5 + the +0.5 in the formula = 2px wide.
        ring_half_stroke = ss_factor * 0.5

        alpha_frac = np.zeros_like(r)
        for b in boundaries[1:]:
            frac = b / album_dur
            r_ring = size * OUTER_GROOVE - frac * groove_range
            ring_alpha = np.clip(ring_half_stroke - np.abs(r - r_ring) + 0.5, 0.0, 1.0)
            alpha_frac = np.maximum(alpha_frac, ring_alpha)

        alpha_val = color[3] if len(color) == 4 else 255
        alpha = (alpha_frac * alpha_val).astype(np.uint8)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = color[0]
        rgba[..., 1] = color[1]
        rgba[..., 2] = color[2]
        rgba[..., 3] = alpha

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    @staticmethod
    def _blit_disc_fill(surf, size, img):
        """Blit a prerendered fractal disc so it fills the full record radius.

        The cached patterns leave a transparent margin (the disc is masked at
        ~0.95–0.97 of the frame, and it differs per pattern family). Auto-detect
        each disc's actual opaque extent and scale so it reaches radius `size`,
        then mask to a clean circle — so patterns match the full-size colored
        and album-art discs regardless of their individual inset.
        """
        d = size * 2
        bb = img.get_bounding_rect(min_alpha=1)
        if bb.width > 0 and bb.height > 0:
            iw, ih = img.get_size()
            scale = d / max(bb.width, bb.height)
            scaled = pygame.transform.smoothscale(
                img, (max(1, round(iw * scale)), max(1, round(ih * scale))))
            # Map the opaque bbox center onto the disc center.
            ox = round(size - (bb.x + bb.width / 2.0) * scale)
            oy = round(size - (bb.y + bb.height / 2.0) * scale)
            surf.blit(scaled, (ox, oy))
        else:
            surf.blit(pygame.transform.smoothscale(img, (d, d)), (0, 0))

        # Clean circular edge at the full radius (also crops any overscan).
        mask = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (size, size), size)
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    def _draw_mandelbrot_vinyl(self, surf, size, center, variant):
        """Draw a vinyl with a Mandelbrot set pattern. Uses pre-rendered cache if available."""
        name = variant[4]
        color = variant[5]
        cache_path = os.path.join(CACHE_DIR, f'{name}-{color}.png')

        if os.path.isfile(cache_path):
            img = pygame.image.load(cache_path)
        else:
            img = _render_mandelbrot_surface(variant, size)

        self._blit_disc_fill(surf, size, img)

    def _draw_munafo_vinyl(self, surf, size, center, variant):
        """Draw a vinyl with a Munafo deep-zoom pattern. Uses the 1600x1600
        pre-rendered cache; falls back to downsampling the 9000x9000 gold
        archive on the fly if the cache is missing (slow first frame)."""
        config_name = variant[0]
        cache_path = os.path.join(MUNAFO_CACHE_DIR, f'{config_name}.png')

        if os.path.isfile(cache_path):
            img = pygame.image.load(cache_path)
        else:
            img = _render_munafo_surface(variant, size)

        self._blit_disc_fill(surf, size, img)

    def _draw_nebula_vinyl(self, surf, size, center, variant):
        """Draw a vinyl with a nebula pattern. Uses pre-rendered cache if available."""
        name = variant[2]
        cache_path = os.path.join(NEBULA_CACHE_DIR, f'{name}.png')

        if os.path.isfile(cache_path):
            img = pygame.image.load(cache_path)
        else:
            img = _render_nebula_surface(variant, size)

        self._blit_disc_fill(surf, size, img)

    def _render(self):
        status = self._status_cache or self.player.get_status()

        if not status.get('playing'):
            self._render_idle()
        else:
            self._render_playing(status)

    def _render_idle(self):
        self._record_rect = None
        self.renderer.draw_color = DARK_BG
        self.renderer.clear()

        tex, rect = self._text_tex('idle_lp', self._font_idle, 'lp', DIM_TEXT)
        dst = rect.copy()
        dst.center = (self.width // 2, self.height // 2 - int(self.height * 0.05))
        tex.draw(dstrect=dst)

        tex, rect = self._text_tex('idle_url', self._font_small, self.url, DIM_TEXT)
        dst = rect.copy()
        dst.center = (self.width // 2, self.height // 2 + int(self.height * 0.08))
        tex.draw(dstrect=dst)

    def _render_playing(self, status):
        self.renderer.draw_color = DARK_BG
        self.renderer.clear()

        art_width = int(self.height * 1.0)
        if art_width > int(self.width * 0.56):
            art_width = int(self.width * 0.56)
        meta_x = art_width
        meta_width = self.width - art_width

        # Album art — upload to a Texture once per art change
        art_path, _ = self.player.get_current_song_info()
        if art_path != self._art_path:
            self._art_path = art_path
            self._art_texture = None
            if art_path:
                try:
                    img = pygame.image.load(art_path)
                    art_surf = pygame.transform.smoothscale(img, (art_width, self.height))
                    self._art_texture = sdl2_video.Texture.from_surface(self.renderer, art_surf)
                except Exception:
                    self._art_texture = None

        if self._art_texture:
            self._art_texture.draw(dstrect=pygame.Rect(0, 0, art_width, self.height))
        else:
            self.renderer.draw_color = PANEL_BG
            self.renderer.fill_rect(pygame.Rect(0, 0, art_width, self.height))

        # Metadata panel
        self.renderer.draw_color = PANEL_BG
        self.renderer.fill_rect(pygame.Rect(meta_x, 0, meta_width, self.height))

        pad = int(meta_width * 0.08)
        x = meta_x + pad
        y = int(self.height * 0.08)

        # Artist
        if status.get('artist'):
            tex, rect = self._text_tex('artist', self._font_large, status['artist'], TEXT_COLOR)
            tex.draw(dstrect=pygame.Rect(x, y, rect.w, rect.h))
            y += rect.h + int(self.height * 0.015)

        # Album
        if status.get('album'):
            tex, rect = self._text_tex('album', self._font_large, status['album'], ACCENT)
            tex.draw(dstrect=pygame.Rect(x, y, rect.w, rect.h))
            y += rect.h + int(self.height * 0.012)

        # Year
        date = status.get('date') or ''
        year = date[:4] if len(date) >= 4 else date
        if year:
            tex, rect = self._text_tex('year', self._font_medium, year, DIM_TEXT)
            tex.draw(dstrect=pygame.Rect(x, y, rect.w, rect.h))
            y += rect.h + int(self.height * 0.02)

        # Spinning record — size to fit remaining space
        progress = status.get('progress', {})
        album_dur = progress.get('album_duration', 0)
        elapsed = progress.get('elapsed', 0)
        boundaries = progress.get('track_boundaries', [])

        remaining_h = self.height - y - int(self.height * 0.06)
        max_by_width = (meta_width - pad * 2) // 2
        record_size = min(remaining_h // 2, max_by_width)
        record_size = max(record_size, 40)

        # Get album path for vinyl style
        album_path = None
        with self.player._lock:
            album_path = self.player.album_path

        # Body: supersampled texture, GPU downscales 2:1 during draw.
        body_key = (album_path, self.player.vinyl_style, self.player.vinyl_label,
                    self.player.vinyl_brightness, record_size, 'body',
                    self.player.vinyl_label_text, self.player.vinyl_label_font,
                    self.player.vinyl_label_artist_color, self.player.vinyl_label_album_color,
                    self.player.vinyl_label_decor1, self.player.vinyl_label_decor1_color,
                    self.player.vinyl_label_decor2, self.player.vinyl_label_decor2_color,
                    status.get('artist'), status.get('album'))
        if body_key != self._record_texture_key:
            self._record_texture_key = body_key
            record_surf = self._build_record(record_size * RECORD_SUPERSAMPLE,
                                             boundaries, album_dur, art_path, album_path,
                                             status.get('artist'), status.get('album'))
            self._record_texture = sdl2_video.Texture.from_surface(self.renderer, record_surf)

        # Grooves overlay: display-resolution texture, no GPU downscale,
        # rotated with the body. Avoids moiré from sampling dense rings.
        style = self._get_vinyl_style(album_path) or {'type': 'black'}
        grooves_key = (style.get('type'), style.get('color'), style.get('variant'),
                       self.player.vinyl_brightness, record_size, tuple(boundaries))
        if grooves_key != self._grooves_texture_key:
            self._grooves_texture_key = grooves_key
            grooves_surf, blend_mode = self._build_grooves_overlay(record_size, style, boundaries, album_dur)
            self._grooves_texture = sdl2_video.Texture.from_surface(self.renderer, grooves_surf)
            self._grooves_texture.blend_mode = (
                pygame.BLENDMODE_ADD if blend_mode == 'add' else pygame.BLENDMODE_BLEND)

        # Specular shine: built per (style type, brightness, size) — independent
        # of rotation and album, since it's the fixed room-light reflection.
        shine_key = (style.get('type'), self.player.vinyl_brightness, record_size)
        if shine_key != self._shine_texture_key:
            self._shine_texture_key = shine_key
            shine_surf = self._build_shine_overlay(record_size, style)
            self._shine_texture = sdl2_video.Texture.from_surface(self.renderer, shine_surf)
            self._shine_texture.blend_mode = pygame.BLENDMODE_BLEND

        rec_cx = meta_x + meta_width // 2
        rec_cy = y + record_size + int(self.height * 0.01)
        d = record_size * 2
        rec_dst = pygame.Rect(rec_cx - record_size, rec_cy - record_size, d, d)
        self._record_rect = rec_dst
        self._record_texture.draw(dstrect=rec_dst, angle=self._record_angle)
        self._grooves_texture.draw(dstrect=rec_dst, angle=self._record_angle)
        # Drawn WITHOUT angle — the reflection stays fixed as the disc spins.
        self._shine_texture.draw(dstrect=rec_dst)

        # Needle — drawn on top, not rotating with the record
        if album_dur > 0:
            frac = min(elapsed / album_dur, 1.0)
        else:
            frac = 0.0
        groove_range = (OUTER_GROOVE - INNER_GROOVE) * record_size
        needle_r = record_size * OUTER_GROOVE - frac * groove_range
        needle_angle = math.radians(-60)
        needle_x = int(rec_cx + needle_r * math.cos(needle_angle))
        needle_y = int(rec_cy + needle_r * math.sin(needle_angle))

        # Tonearm — two parallel lines to simulate the old width=2
        pivot_x = int(rec_cx + record_size * 1.15)
        pivot_y = int(rec_cy - record_size * 0.9)
        self.renderer.draw_color = (70, 70, 70)
        self.renderer.draw_line((pivot_x, pivot_y), (needle_x, needle_y))
        self.renderer.draw_line((pivot_x, pivot_y + 1), (needle_x, needle_y + 1))

        # Needle dot — pre-built tiny texture
        self._needle_tex.draw(dstrect=pygame.Rect(needle_x - 4, needle_y - 4, 9, 9))
