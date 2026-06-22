"""Vinyl option catalog — the small, self-contained lists of what a user can
pick, used for validation and for enumerating UI controls.

This is the seed of the single source of truth for vinyl options. The large
style/colour/variant tables and rendering palettes still live in lp.display for
now; they move here alongside the renderer in the next step, at which point this
module also grows an ``enumerate_options()`` that both the web UI and lp-deck
read from instead of rebuilding lists.
"""

# Label text rendering modes.
LABEL_TEXT_MODES = ['none', 'curved', 'straight', 'blocky']

# Fonts available for the curved/straight/blocky label text.
LABEL_TEXT_FONTS = ['georgia', 'dejavuserif', 'dejavusans', 'dejavusansmono',
                    'oswald', 'bebasneue', 'notoserif', 'notosans', 'ubuntu',
                    'cantarell']

# Decorative critters for the label's empty spaces (rendered via the Noto Color
# Emoji font). Name → emoji; the names double as the valid decor values.
DECOR_EMOJI = {
    'bird': '🐦', 'dove': '🕊', 'owl': '🦉',
    'sun': '☀', 'moon': '🌙', 'star': '⭐',
    'octopus': '🐙', 'fish': '🐟',
    'beaver': '🦫', 'dog': '🐕', 'cat': '🐈',
}

# Valid values for a decor slot: a critter name, or these specials.
DECOR_VALUES = ('none', 'random', *DECOR_EMOJI.keys())


# --- Vinyl style/colour/variant tables (relocated from lp.display) ---

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

# Background / spindle-hole colour (also lp.display window bg).
DARK_BG = (17, 17, 17)
