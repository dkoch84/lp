import math
import os
import random
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
}

# Per-variant groove + track-mark appearance — (groove_rgba, track_rgba).
# Dark body → light groove (highlight), light body → dark groove (shadow).
# Track alpha is roughly 2× groove alpha so boundaries are visible but not huge.
# Tune these to taste per vinyl style.
VINYL_GROOVE_COLORS = {
    # Light bodies — dark shadow haze (subtle)
    'cream':      ((0, 0, 0, 7),        (0, 0, 0, 28)),
    'mono':       ((0, 0, 0, 7),        (0, 0, 0, 28)),
    'fire':       ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'gold':       ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'ocean':      ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'emerald':    ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'lavender':   ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'purple':     ((0, 0, 0, 10),       (0, 0, 0, 40)),
    'rose':       ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'copper':     ((0, 0, 0, 9),        (0, 0, 0, 36)),
    'rust':       ((0, 0, 0, 10),       (0, 0, 0, 40)),
    # Dark bodies — light additive shine
    'red':        ((255, 255, 255, 8),  (255, 255, 255, 45)),
    'navy':       ((255, 255, 255, 8),  (255, 255, 255, 45)),
    'forest':     ((255, 255, 255, 8),  (255, 255, 255, 45)),
    'plum':       ((255, 255, 255, 8),  (255, 255, 255, 45)),
    'chocolate':  ((255, 255, 255, 8),  (255, 255, 255, 45)),
    'slate':      ((255, 255, 255, 7),  (255, 255, 255, 36)),
    'amber':      ((255, 255, 255, 8),  (255, 255, 255, 45)),
    'teal':       ((255, 255, 255, 8),  (255, 255, 255, 45)),
    'burgundy':   ((255, 255, 255, 8),  (255, 255, 255, 45)),
    'olive':      ((255, 255, 255, 8),  (255, 255, 255, 45)),
    'midnight':   ((255, 255, 255, 8),  (255, 255, 255, 45)),
}

# Plain black vinyl: light grooves (light catching the spiral) on a dark body.
BLACK_GROOVE_COLORS = ((90, 90, 90, 80), (110, 110, 110, 130))

# Transparent / clear vinyl.
CLEAR_GROOVE_COLORS = ((255, 255, 255, 10), (255, 255, 255, 22))

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

# Style weights
STYLE_DISTRIBUTION = [
    ('black', 15),
    ('color', 15),
    ('mandelbrot', 25),
    ('nebula', 25),
    ('clear', 10),
    ('picture', 10),
]


CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache', 'mandelbrot')
NEBULA_CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache', 'nebula')

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


def _render_nebula_surface(variant, size):
    """Render a nebula-style vinyl disc. Vectorized over the full pixel grid."""
    seed, palette_fn, _name, sat, warp_oct, arm_oct = variant
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


def prerender_all():
    """Pre-render all mandelbrot and nebula variants to PNG cache. Run once on a fast machine."""
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

    os.makedirs(NEBULA_CACHE_DIR, exist_ok=True)
    for variant in NEBULA_VARIANTS:
        name = variant[2]
        path = os.path.join(NEBULA_CACHE_DIR, f'{name}.png')
        print(f'  rendering nebula/{name} at {PRERENDER_SIZE}px radius...', end=' ', flush=True)
        surf = _render_nebula_surface(variant, PRERENDER_SIZE)
        pygame.image.save(surf, path)
        print('done')
    print(f'cached {len(NEBULA_VARIANTS)} nebula variants in {NEBULA_CACHE_DIR}')


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
        self._text_cache = {}
        self._needle_tex = None

        self.window = None
        self.renderer = None

        player.on('play_start', self._mark_dirty)
        player.on('track_change', self._mark_dirty)
        player.on('album_end', self._mark_dirty)
        player.on('stop', self._mark_dirty)

    def _mark_dirty(self):
        self._dirty = True

    def run(self):
        # Tell SDL to use linear filtering when sampling textures. Without this,
        # SDL defaults to nearest-neighbor and the supersampled record texture
        # rotates with stair-stepped edges. Must be set before Renderer is created.
        os.environ.setdefault('SDL_HINT_RENDER_SCALE_QUALITY', '2')

        pygame.init()
        pygame.mixer.quit()  # Release audio device for VLC

        if self.fullscreen:
            self.window = sdl2_video.Window('lp', size=(self.width, self.height),
                                            fullscreen_desktop=True)
            self.width, self.height = self.window.size
        else:
            self.window = sdl2_video.Window('lp', size=(self.width, self.height))

        try:
            self.renderer = sdl2_video.Renderer(self.window, accelerated=1, vsync=True)
            print(f'display: GPU renderer at {self.width}x{self.height} (SS={RECORD_SUPERSAMPLE})', flush=True)
        except pygame.error as e:
            print(f'WARN: GPU renderer unavailable ({e}); falling back to software', flush=True)
            self.renderer = sdl2_video.Renderer(self.window, accelerated=0)

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
                    if event.key == pygame.K_ESCAPE:
                        running = False

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

            self.clock.tick(30)

        pygame.quit()

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

    def _get_vinyl_style(self, album_path):
        """Get or compute vinyl style for current album."""
        override = self.player.vinyl_style
        cache_key = (album_path, override)
        if cache_key != (self._current_album_path, getattr(self, '_current_override', None)):
            self._current_album_path = album_path
            self._current_override = override
            self._current_vinyl_style = _pick_vinyl_style(album_path, override) if album_path else None
        return self._current_vinyl_style

    def _build_record(self, size, boundaries, album_dur, art_path=None, album_path=None):
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
            pygame.draw.circle(surf, (255, 255, 255, 12), center, size)
            pygame.draw.circle(surf, (255, 255, 255, 40), center, size, 2)
            pygame.draw.circle(surf, (255, 255, 255, 25), center, size - 1, 1)
        elif style_type == 'color':
            base = VINYL_COLORS.get(style.get('color'), VINYL_BLACK[0])
            pygame.draw.circle(surf, base, center, size)
        elif style_type == 'mandelbrot':
            variant = style['variant']
            self._draw_mandelbrot_vinyl(surf, size, center, variant)
        elif style_type == 'nebula':
            variant = style['variant']
            self._draw_nebula_vinyl(surf, size, center, variant)
        else:
            self._draw_black_vinyl(surf, size, center)

        # Label — album art, colored, or fallback (skip for picture disc)
        if style_type != 'picture':
            label_r = int(size * LABEL_RADIUS)
            label_setting = self.player.vinyl_label

            if label_setting == 'art':
                label_art = self._get_label_art(art_path, label_r) if art_path else None
                if label_art:
                    surf.blit(label_art, (size - label_r, size - label_r))
                else:
                    pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                    self._draw_fake_label_text(surf, size, size, label_r, VINYL_LABEL_DARK)
            elif label_setting.startswith('label-'):
                color_name = label_setting[len('label-'):]
                main_c, accent_c = LABEL_COLORS.get(color_name, (VINYL_LABEL, VINYL_LABEL_DARK))
                pygame.draw.circle(surf, main_c, center, label_r)
                self._draw_fake_label_text(surf, size, size, label_r, accent_c)
            else:
                pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                self._draw_fake_label_text(surf, size, size, label_r, VINYL_LABEL_DARK)

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
            overlay_c = CLEAR_GROOVE_COLORS[0]
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
        elif style_type in ('mandelbrot', 'nebula', 'picture'):
            overlay_c = (255, 255, 255, 8)
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

    def _draw_mandelbrot_vinyl(self, surf, size, center, variant):
        """Draw a vinyl with a Mandelbrot set pattern. Uses pre-rendered cache if available."""
        name = variant[4]
        color = variant[5]

        d = size * 2
        cache_path = os.path.join(CACHE_DIR, f'{name}-{color}.png')

        if os.path.isfile(cache_path):
            cached = pygame.image.load(cache_path)
            fractal = pygame.transform.smoothscale(cached, (d, d))
        else:
            fractal = _render_mandelbrot_surface(variant, size)

        surf.blit(fractal, (0, 0))

    def _draw_nebula_vinyl(self, surf, size, center, variant):
        """Draw a vinyl with a nebula pattern. Uses pre-rendered cache if available."""
        name = variant[2]

        d = size * 2
        cache_path = os.path.join(NEBULA_CACHE_DIR, f'{name}.png')

        if os.path.isfile(cache_path):
            cached = pygame.image.load(cache_path)
            nebula = pygame.transform.smoothscale(cached, (d, d))
        else:
            nebula = _render_nebula_surface(variant, size)

        surf.blit(nebula, (0, 0))

    def _render(self):
        status = self._status_cache or self.player.get_status()

        if not status.get('playing'):
            self._render_idle()
        else:
            self._render_playing(status)

    def _render_idle(self):
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
                    self.player.vinyl_brightness, record_size, 'body')
        if body_key != self._record_texture_key:
            self._record_texture_key = body_key
            record_surf = self._build_record(record_size * RECORD_SUPERSAMPLE,
                                             boundaries, album_dur, art_path, album_path)
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
            # SDL_BLENDMODE_ADD = 2, _BLEND = 1
            self._grooves_texture.blend_mode = 2 if blend_mode == 'add' else 1

        rec_cx = meta_x + meta_width // 2
        rec_cy = y + record_size + int(self.height * 0.01)
        d = record_size * 2
        rec_dst = pygame.Rect(rec_cx - record_size, rec_cy - record_size, d, d)
        self._record_texture.draw(dstrect=rec_dst, angle=self._record_angle)
        self._grooves_texture.draw(dstrect=rec_dst, angle=self._record_angle)

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
