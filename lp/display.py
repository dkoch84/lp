import math
import os
import random
import pygame
import pygame.gfxdraw


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
}

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

# Pre-render resolution (radius) — large enough to scale down for any display
PRERENDER_SIZE = 400


# --- Nebula noise helpers ---

def _make_nebula_grids(seed, count=8, grid_size=64):
    """Generate value-noise grids for nebula rendering."""
    rng = random.Random(seed)
    grids = []
    for _ in range(count):
        grid = [[rng.random() for _ in range(grid_size + 1)] for _ in range(grid_size + 1)]
        grids.append((grid_size, grid))
    return grids


def _smoothstep(t):
    return t * t * (3 - 2 * t)


def _noise2d(x, y, gi, grids):
    g, grid = grids[gi % len(grids)]
    x = x % g
    y = y % g
    ix, iy = int(x), int(y)
    fx, fy = _smoothstep(x - ix), _smoothstep(y - iy)
    ix2 = (ix + 1) % g
    iy2 = (iy + 1) % g
    return (grid[iy][ix] * (1 - fx) * (1 - fy) +
            grid[iy][ix2] * fx * (1 - fy) +
            grid[iy2][ix] * (1 - fx) * fy +
            grid[iy2][ix2] * fx * fy)


def _fbm(x, y, octaves, gi, grids):
    val = 0.0
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
    b1 = br * (120 + 135 * (0.5 + 0.5 * math.sin(t1 * 10.0)))
    r2 = br * (200 + 55 * t3)
    g2 = br * (80 + 140 * t1)
    b2 = br * (5 + 40 * (1 - t3))
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_ocean_emerald(br, blend, t1, t2, t3, hs):
    r1 = br * (5 + 50 * hs)
    g1 = br * (80 + 175 * t1)
    b1 = br * (60 + 140 * (0.5 + 0.5 * math.sin(t1 * 8.0)))
    r2 = br * (10 + 40 * t3)
    g2 = br * (40 + 80 * hs)
    b2 = br * (140 + 115 * t1)
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_crimson_gold(br, blend, t1, t2, t3, hs):
    r1 = br * (180 + 75 * t1)
    g1 = br * (15 + 50 * t1)
    b1 = br * (10 + 30 * hs)
    r2 = br * (200 + 55 * t3)
    g2 = br * (140 + 100 * t1)
    b2 = br * (5 + 20 * (1 - t3))
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_electric(br, blend, t1, t2, t3, hs):
    r1 = br * (20 + 60 * hs)
    g1 = br * (100 + 155 * t1)
    b1 = br * (180 + 75 * (0.5 + 0.5 * math.sin(t1 * 6.0)))
    r2 = br * (200 + 55 * t1)
    g2 = br * (20 + 60 * (1 - t3))
    b2 = br * (120 + 100 * hs)
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_emerald_purple(br, blend, t1, t2, t3, hs):
    r1 = br * (10 + 40 * hs)
    g1 = br * (120 + 135 * t1)
    b1 = br * (30 + 60 * t3)
    r2 = br * (100 + 120 * t1)
    g2 = br * (10 + 40 * hs)
    b2 = br * (140 + 115 * (0.5 + 0.5 * math.sin(t1 * 8.0)))
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_deep_emerald(br, blend, t1, t2, t3, hs):
    """No brightness multiplier — noise only shifts hue within green."""
    r = 40 + 30 * blend + 20 * hs
    g = 150 + 60 * t1 + 30 * blend
    b = 65 + 40 * t3 + 20 * (1 - blend)
    return (int(r), int(g), int(b))


def _nebula_bone(br, blend, t1, t2, t3, hs):
    base = 0.4 + 0.6 * br
    r1 = base * (220 + 35 * t1)
    g1 = base * (210 + 30 * hs)
    b1 = base * (185 + 40 * t3)
    r2 = base * (190 + 40 * t3)
    g2 = base * (175 + 35 * t1)
    b2 = base * (155 + 30 * hs)
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_cream_rose(br, blend, t1, t2, t3, hs):
    base = 0.4 + 0.6 * br
    r1 = base * (240 + 15 * t1)
    g1 = base * (215 + 20 * hs)
    b1 = base * (200 + 25 * t3)
    r2 = base * (220 + 35 * t1)
    g2 = base * (160 + 50 * hs)
    b2 = base * (165 + 50 * t3)
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_marble(br, blend, t1, t2, t3, hs):
    base = 0.35 + 0.65 * br
    r1 = base * (230 + 25 * hs)
    g1 = base * (232 + 23 * t1)
    b1 = base * (240 + 15 * t3)
    r2 = base * (140 + 60 * t3)
    g2 = base * (145 + 55 * t1)
    b2 = base * (160 + 60 * hs)
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_cream_green(br, blend, t1, t2, t3, hs):
    base = 0.4 + 0.6 * (0.2 + 0.65 * t1 + 0.3 * t2)
    r1 = base * (225 + 20 * t1)
    g1 = base * (230 + 20 * hs)
    b1 = base * (200 + 20 * t3)
    r2 = base * (185 + 25 * t3)
    g2 = base * (215 + 25 * t1)
    b2 = base * (175 + 20 * hs)
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_galaxy(br, blend, t1, t2, t3, hs):
    br2 = br * br
    r1 = br2 * (80 + 175 * t1)
    g1 = br2 * (30 + 80 * hs)
    b1 = br2 * (120 + 135 * (0.5 + 0.5 * math.sin(t1 * 8.0)))
    r2 = br2 * (20 + 60 * t3)
    g2 = br2 * (15 + 50 * t1)
    b2 = br2 * (80 + 160 * hs)
    star = max(0, t1 * t2 * 4 - 1.2) ** 2
    return (int(r1 * blend + r2 * (1 - blend) + star * 200),
            int(g1 * blend + g2 * (1 - blend) + star * 180),
            int(b1 * blend + b2 * (1 - blend) + star * 255))


def _nebula_galaxy_warm(br, blend, t1, t2, t3, hs):
    br2 = br * br
    r1 = br2 * (160 + 95 * t1)
    g1 = br2 * (20 + 80 * hs)
    b1 = br2 * (100 + 120 * t3)
    r2 = br2 * (180 + 75 * t3)
    g2 = br2 * (80 + 120 * t1)
    b2 = br2 * (15 + 40 * hs)
    star = max(0, t1 * t2 * 4 - 1.2) ** 2
    return (int(r1 * blend + r2 * (1 - blend) + star * 220),
            int(g1 * blend + g2 * (1 - blend) + star * 200),
            int(b1 * blend + b2 * (1 - blend) + star * 160))


def _nebula_galaxy_cold(br, blend, t1, t2, t3, hs):
    br2 = br * br
    r1 = br2 * (15 + 60 * hs)
    g1 = br2 * (80 + 140 * t1)
    b1 = br2 * (160 + 95 * (0.5 + 0.5 * math.sin(t1 * 6.0)))
    r2 = br2 * (30 + 50 * t3)
    g2 = br2 * (40 + 80 * t1)
    b2 = br2 * (130 + 125 * hs)
    star = max(0, t1 * t2 * 4 - 1.2) ** 2
    return (int(r1 * blend + r2 * (1 - blend) + star * 180),
            int(g1 * blend + g2 * (1 - blend) + star * 220),
            int(b1 * blend + b2 * (1 - blend) + star * 255))


def _nebula_oil_spill(br, blend, t1, t2, t3, hs):
    r1 = br * (60 + 90 * t1)
    g1 = br * (80 + 100 * hs)
    b1 = br * (100 + 80 * t3)
    r2 = br * (130 + 70 * t3)
    g2 = br * (50 + 60 * t1)
    b2 = br * (60 + 70 * hs)
    pop = max(0, t1 * t2 * 3 - 0.9)
    return (int(r1 * blend + r2 * (1 - blend) + pop * 80),
            int(g1 * blend + g2 * (1 - blend) + pop * 100),
            int(b1 * blend + b2 * (1 - blend) + pop * 90))


def _nebula_absinthe(br, blend, t1, t2, t3, hs):
    r1 = br * (60 + 80 * hs)
    g1 = br * (150 + 80 * t1)
    b1 = br * (30 + 50 * t3)
    r2 = br * (100 + 80 * t1)
    g2 = br * (30 + 50 * hs)
    b2 = br * (90 + 80 * t3)
    pop = max(0, t1 * t2 * 3 - 0.85)
    return (int(r1 * blend + r2 * (1 - blend) + pop * 120),
            int(g1 * blend + g2 * (1 - blend) + pop * 70),
            int(b1 * blend + b2 * (1 - blend) + pop * 30))


def _nebula_coral_reef(br, blend, t1, t2, t3, hs):
    r1 = br * (200 + 40 * t1)
    g1 = br * (90 + 60 * hs)
    b1 = br * (80 + 50 * t3)
    r2 = br * (40 + 60 * t3)
    g2 = br * (140 + 80 * t1)
    b2 = br * (130 + 70 * hs)
    pop = max(0, t1 * t2 * 3 - 0.9)
    return (int(r1 * blend + r2 * (1 - blend) + pop * 60),
            int(g1 * blend + g2 * (1 - blend) + pop * 90),
            int(b1 * blend + b2 * (1 - blend) + pop * 40))


def _nebula_bruise(br, blend, t1, t2, t3, hs):
    r1 = br * (80 + 80 * t1)
    g1 = br * (20 + 50 * hs)
    b1 = br * (120 + 100 * t3)
    r2 = br * (120 + 60 * t3)
    g2 = br * (110 + 60 * t1)
    b2 = br * (30 + 40 * hs)
    return (int(r1 * blend + r2 * (1 - blend)),
            int(g1 * blend + g2 * (1 - blend)),
            int(b1 * blend + b2 * (1 - blend)))


def _nebula_molten(br, blend, t1, t2, t3, hs):
    r1 = br * (190 + 50 * t1)
    g1 = br * (80 + 70 * t1)
    b1 = br * (20 + 40 * hs)
    r2 = br * (140 + 60 * t3)
    g2 = br * (25 + 40 * hs)
    b2 = br * (50 + 60 * t1)
    pop = max(0, t1 * t2 * 3 - 0.85)
    return (int(r1 * blend + r2 * (1 - blend) + pop * 100),
            int(g1 * blend + g2 * (1 - blend) + pop * 120),
            int(b1 * blend + b2 * (1 - blend) + pop * 20))


def _nebula_lava_lamp(br, blend, t1, t2, t3, hs):
    r1 = br * (200 + 55 * t1)
    g1 = br * (40 + 80 * t1)
    b1 = br * (10 + 50 * hs)
    r2 = br * (120 + 80 * t3)
    g2 = br * (10 + 30 * hs)
    b2 = br * (140 + 115 * t1)
    pop = max(0, t1 * t2 * 3 - 0.9)
    return (int(r1 * blend + r2 * (1 - blend) + pop * 200),
            int(g1 * blend + g2 * (1 - blend) + pop * 180),
            int(b1 * blend + b2 * (1 - blend) + pop * 30))


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


def _render_nebula_surface(variant, size):
    """Render a nebula-style vinyl disc. Returns a pygame Surface."""
    seed, palette_fn, _name, sat, warp_oct, arm_oct = variant
    grids = _make_nebula_grids(seed)

    d = size * 2
    sm = max(size // 2, 40)
    d_sm = sm * 2
    surf = pygame.Surface((d_sm, d_sm), pygame.SRCALPHA)
    sc = sm
    max_r_sq = (sm * 0.95) ** 2

    for py in range(d_sm):
        for px in range(d_sm):
            dx, dy = px - sc, py - sc
            if dx * dx + dy * dy > max_r_sq:
                continue
            dist = math.sqrt(dx * dx + dy * dy) / sm
            angle = math.atan2(dy, dx)

            nx = px / sm * 3.0
            ny = py / sm * 3.0

            wx = nx + _fbm(nx + 1.7, ny + 9.2, warp_oct, 0, grids) * 3.0
            wy = ny + _fbm(nx + 8.3, ny + 2.8, warp_oct, 2, grids) * 3.0
            wx2 = wx + _fbm(wx * 0.8 + 3.1, wy * 0.8 + 7.7, max(warp_oct - 1, 2), 4, grids) * 2.0
            wy2 = wy + _fbm(wx * 0.8 + 1.3, wy * 0.8 + 4.9, max(warp_oct - 1, 2), 6, grids) * 2.0

            sa = math.sin(angle * 2.0) * dist * 2.5
            ca = math.cos(angle * 2.0) * dist * 2.5
            arm = _fbm(wx2 + sa, wy2 + ca, arm_oct, 1, grids)
            cloud1 = _fbm(wx2 * 1.2, wy2 * 1.2, arm_oct, 3, grids)
            cloud2 = _fbm(wx2 * 0.7 + 20, wy2 * 0.7 + 20, max(arm_oct - 1, 3), 5, grids)

            t1, t2, t3 = arm, cloud1, cloud2
            brightness = 0.2 + 0.65 * t1 + 0.3 * t2
            brightness *= (1.0 - dist * 0.3)
            brightness = max(0.0, min(1.0, (brightness - 0.15) * 1.4))
            hue_shift = _fbm(nx * 0.8, ny * 0.8, 3, 0, grids)
            blend = _smoothstep(max(0.0, min(1.0, (t1 - 0.3) * 2.5)))

            r, g, b = palette_fn(brightness, blend, t1, t2, t3, hue_shift)

            avg = (r + g + b) / 3.0
            r = int(avg + (r - avg) * sat)
            g = int(avg + (g - avg) * sat)
            b = int(avg + (b - avg) * sat)

            if dist < 0.2:
                core = (1 - dist / 0.2) ** 2
                r = int(r + core * (255 - r) * 0.7)
                g = int(g + core * (220 - g) * 0.5)
                b = int(b + core * (255 - b) * 0.6)

            surf.set_at((px, py), (min(255, max(0, r)),
                                   min(255, max(0, g)),
                                   min(255, max(0, b)), 255))

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
    """Render a mandelbrot fractal disc at given radius. Returns a pygame Surface."""
    cx_m, cy_m, zoom, max_iter, _name, color_key = variant
    scheme = MANDELBROT_COLORS.get(color_key, MANDELBROT_COLORS['purple'])
    base_dark, r_p, g_p, b_p, _groove, _track = scheme

    d = size * 2
    sm = max(size // 2, 40)
    d_sm = sm * 2
    sm_surf = pygame.Surface((d_sm, d_sm), pygame.SRCALPHA)
    sc = sm
    max_r_sq = (sm * 0.95) ** 2

    for py in range(d_sm):
        for px in range(d_sm):
            dx, dy = px - sc, py - sc
            if dx * dx + dy * dy > max_r_sq:
                continue
            cr = cx_m + (px - sc) / sm / zoom
            ci = cy_m + (py - sc) / sm / zoom
            zr, zi = 0.0, 0.0
            i = 0
            while zr * zr + zi * zi <= 4.0 and i < max_iter:
                zr, zi = zr * zr - zi * zi + cr, 2.0 * zr * zi + ci
                i += 1
            if i == max_iter:
                color = base_dark
            else:
                t = i / max_iter
                r = int(r_p[0] + r_p[1] * (0.5 + 0.5 * math.sin(t * r_p[2] + r_p[3])))
                g = int(g_p[0] + g_p[1] * (0.5 + 0.5 * math.sin(t * g_p[2] + g_p[3])))
                b = int(b_p[0] + b_p[1] * (0.5 + 0.5 * math.sin(t * b_p[2] + b_p[3])))
                color = (min(255, r), min(255, g), min(255, b))
            sm_surf.set_at((px, py), (*color, 255))

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
        self._art_surface = None
        self._art_path = None
        self._status_cache = None
        self._record_angle = 0.0
        self._label_art = None
        self._label_art_path = None
        self._current_vinyl_style = None
        self._current_album_path = None
        self._record_cache = None
        self._record_cache_key = None

        player.on('play_start', self._mark_dirty)
        player.on('track_change', self._mark_dirty)
        player.on('album_end', self._mark_dirty)
        player.on('stop', self._mark_dirty)

    def _mark_dirty(self):
        self._dirty = True

    def run(self):
        pygame.init()
        pygame.mixer.quit()  # Release audio device for VLC
        pygame.display.set_caption('lp')

        flags = 0
        if self.fullscreen:
            flags = pygame.FULLSCREEN
            info = pygame.display.Info()
            self.width = info.current_w
            self.height = info.current_h

        self.screen = pygame.display.set_mode((self.width, self.height), flags)
        self.clock = pygame.time.Clock()

        self._load_fonts()
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
                pygame.display.flip()

            self.clock.tick(30)

        pygame.quit()

    def _load_fonts(self):
        self._font_large = pygame.font.SysFont('sans', int(self.height * 0.03))
        self._font_medium = pygame.font.SysFont('sans', int(self.height * 0.026))
        self._font_small = pygame.font.SysFont('sans', int(self.height * 0.02))
        self._font_idle = pygame.font.SysFont('sans', int(self.height * 0.12))

    def _get_circular_art(self, art_path, radius):
        """Get album art masked into a circle at the given radius."""
        try:
            img = pygame.image.load(art_path).convert_alpha()
            d = radius * 2
            scaled = pygame.transform.smoothscale(img, (d, d))
            circle_mask = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(circle_mask, (255, 255, 255, 255), (radius, radius), radius)
            scaled.blit(circle_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            return scaled
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
        """Build the vinyl record surface with track boundary marks and style."""
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
                self._draw_grooves(surf, size, center, (0, 0, 0, 12))
                self._draw_track_marks(surf, size, center, (0, 0, 0, 25), boundaries, album_dur)
            else:
                self._draw_black_vinyl(surf, size, center, boundaries, album_dur)
        elif style_type == 'clear':
            pygame.draw.circle(surf, (255, 255, 255, 12), center, size)
            self._draw_grooves(surf, size, center, (255, 255, 255, 10))
            self._draw_track_marks(surf, size, center, (255, 255, 255, 22), boundaries, album_dur)
            pygame.draw.circle(surf, (255, 255, 255, 40), center, size, 2)
            pygame.draw.circle(surf, (255, 255, 255, 25), center, size - 1, 1)
        elif style_type == 'color':
            base = VINYL_COLORS.get(style.get('color'), VINYL_BLACK[0])
            pygame.draw.circle(surf, base, center, size)
            self._draw_grooves(surf, size, center, (0, 0, 0, 14))
            self._draw_track_marks(surf, size, center, (0, 0, 0, 28), boundaries, album_dur)
        elif style_type == 'mandelbrot':
            variant = style['variant']
            self._draw_mandelbrot_vinyl(surf, size, center, variant, boundaries, album_dur)
        elif style_type == 'nebula':
            variant = style['variant']
            self._draw_nebula_vinyl(surf, size, center, variant, boundaries, album_dur)
        else:
            self._draw_black_vinyl(surf, size, center, boundaries, album_dur)

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


    @staticmethod
    def _draw_grooves(surf, size, center, color, spacing=3):
        """Draw anti-aliased groove circles via 2x supersampling.

        Uses a dark semi-transparent overlay to subtly darken existing pixels,
        simulating how light catches real vinyl grooves.
        """
        d = size * 2
        scale = 2
        hi_d = d * scale
        hi_c = (size * scale, size * scale)
        hi = pygame.Surface((hi_d, hi_d), pygame.SRCALPHA)
        for r in range(int(size * scale * INNER_GROOVE), int(size * scale * OUTER_GROOVE), spacing * scale):
            pygame.draw.circle(hi, color, hi_c, r, 1)
        scaled = pygame.transform.smoothscale(hi, (d, d))
        surf.blit(scaled, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    def _draw_black_vinyl(self, surf, size, center, boundaries, album_dur):
        """Draw a plain black vinyl with grooves and track marks."""
        base, groove, track_mark = VINYL_BLACK
        pygame.draw.circle(surf, base, center, size)
        # Black vinyl: groove is a lighter shade of the base (light catching edges)
        self._draw_grooves(surf, size, center, groove)
        self._draw_track_marks(surf, size, center, track_mark, boundaries, album_dur)

    def _draw_track_marks(self, surf, size, center, color, boundaries, album_dur):
        """Draw anti-aliased track boundary rings — slightly more visible than grooves."""
        if album_dur > 0 and boundaries:
            groove_range = (OUTER_GROOVE - INNER_GROOVE) * size
            d = size * 2
            scale = 2
            hi = pygame.Surface((d * scale, d * scale), pygame.SRCALPHA)
            hi_c = (size * scale, size * scale)
            for b in boundaries[1:]:
                frac = b / album_dur
                r = int(size * scale * OUTER_GROOVE - frac * groove_range * scale)
                pygame.draw.circle(hi, color, hi_c, r, 1)
            scaled = pygame.transform.smoothscale(hi, (d, d))
            surf.blit(scaled, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    def _draw_mandelbrot_vinyl(self, surf, size, center, variant, boundaries, album_dur):
        """Draw a vinyl with a Mandelbrot set pattern. Uses pre-rendered cache if available."""
        name = variant[4]
        color = variant[5]

        d = size * 2
        cache_path = os.path.join(CACHE_DIR, f'{name}-{color}.png')

        if os.path.isfile(cache_path):
            cached = pygame.image.load(cache_path).convert_alpha()
            fractal = pygame.transform.smoothscale(cached, (d, d))
        else:
            fractal = _render_mandelbrot_surface(variant, size)

        surf.blit(fractal, (0, 0))

        # Subtle grooves — dark semi-transparent overlay
        self._draw_grooves(surf, size, center, (0, 0, 0, 14))
        # Track marks slightly more visible
        self._draw_track_marks(surf, size, center, (0, 0, 0, 30), boundaries, album_dur)

    def _draw_nebula_vinyl(self, surf, size, center, variant, boundaries, album_dur):
        """Draw a vinyl with a nebula pattern. Uses pre-rendered cache if available."""
        name = variant[2]

        d = size * 2
        cache_path = os.path.join(NEBULA_CACHE_DIR, f'{name}.png')

        if os.path.isfile(cache_path):
            cached = pygame.image.load(cache_path).convert_alpha()
            nebula = pygame.transform.smoothscale(cached, (d, d))
        else:
            nebula = _render_nebula_surface(variant, size)

        surf.blit(nebula, (0, 0))

        # Subtle grooves — dark semi-transparent overlay
        self._draw_grooves(surf, size, center, (0, 0, 0, 14))
        # Track marks slightly more visible
        self._draw_track_marks(surf, size, center, (0, 0, 0, 30), boundaries, album_dur)

    def _render(self):
        status = self._status_cache or self.player.get_status()

        if not status.get('playing'):
            self._render_idle()
        else:
            self._render_playing(status)

    def _render_idle(self):
        self.screen.fill(DARK_BG)
        text = self._font_idle.render('lp', True, DIM_TEXT)
        rect = text.get_rect(center=(self.width // 2, self.height // 2 - int(self.height * 0.05)))
        self.screen.blit(text, rect)

        url_surf = self._font_small.render(self.url, True, DIM_TEXT)
        url_rect = url_surf.get_rect(center=(self.width // 2, self.height // 2 + int(self.height * 0.08)))
        self.screen.blit(url_surf, url_rect)

    def _render_playing(self, status):
        self.screen.fill(DARK_BG)

        art_width = int(self.height * 1.0)
        if art_width > int(self.width * 0.56):
            art_width = int(self.width * 0.56)
        meta_x = art_width
        meta_width = self.width - art_width

        # Album art
        art_path, _ = self.player.get_current_song_info()
        if art_path and art_path != self._art_path:
            self._art_path = art_path
            try:
                img = pygame.image.load(art_path)
                self._art_surface = pygame.transform.smoothscale(img, (art_width, self.height))
            except Exception:
                self._art_surface = None

        if self._art_surface:
            self.screen.blit(self._art_surface, (0, 0))
        else:
            pygame.draw.rect(self.screen, PANEL_BG, (0, 0, art_width, self.height))

        # Metadata panel
        pygame.draw.rect(self.screen, PANEL_BG, (meta_x, 0, meta_width, self.height))

        pad = int(meta_width * 0.08)
        x = meta_x + pad
        y = int(self.height * 0.08)

        # Artist
        if status.get('artist'):
            surf = self._font_large.render(status['artist'], True, TEXT_COLOR)
            self.screen.blit(surf, (x, y))
            y += surf.get_height() + int(self.height * 0.015)

        # Album
        if status.get('album'):
            surf = self._font_large.render(status['album'], True, ACCENT)
            self.screen.blit(surf, (x, y))
            y += surf.get_height() + int(self.height * 0.012)

        # Year
        date = status.get('date') or ''
        year = date[:4] if len(date) >= 4 else date
        if year:
            surf = self._font_medium.render(year, True, DIM_TEXT)
            self.screen.blit(surf, (x, y))
            y += surf.get_height() + int(self.height * 0.02)

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

        # Cache the record surface — only rebuild when album/style/size changes
        cache_key = (album_path, self.player.vinyl_style, self.player.vinyl_label,
                     self.player.vinyl_brightness, record_size, tuple(boundaries))
        if cache_key != self._record_cache_key:
            self._record_cache_key = cache_key
            self._record_cache = self._build_record(record_size, boundaries, album_dur, art_path, album_path)
        record_surf = self._record_cache
        rotated = pygame.transform.rotate(record_surf, self._record_angle)
        rec_cx = meta_x + meta_width // 2
        rec_cy = y + record_size + int(self.height * 0.01)
        rec_rect = rotated.get_rect(center=(rec_cx, rec_cy))
        self.screen.blit(rotated, rec_rect)

        # Needle — drawn on top, not rotating with the record
        if album_dur > 0:
            frac = min(elapsed / album_dur, 1.0)
        else:
            frac = 0.0
        groove_range = (OUTER_GROOVE - INNER_GROOVE) * record_size
        needle_r = record_size * OUTER_GROOVE - frac * groove_range
        needle_angle = math.radians(-60)
        needle_x = rec_cx + needle_r * math.cos(needle_angle)
        needle_y = rec_cy + needle_r * math.sin(needle_angle)

        # Tonearm line from pivot to needle tip
        pivot_x = rec_cx + record_size * 1.15
        pivot_y = rec_cy - record_size * 0.9
        pygame.draw.line(self.screen, (70, 70, 70), (pivot_x, pivot_y), (int(needle_x), int(needle_y)), 2)
        pygame.draw.circle(self.screen, NEEDLE_COLOR, (int(needle_x), int(needle_y)), 3)
