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

# Black vinyl body colour.
VINYL_BLACK = (40, 40, 40)

# Coloured vinyl body colours, as rgb.
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
    'sea-foam':     (124, 147, 133),
}

# Groove haze colour per vinyl colour, as rgba. Dark bodies get a light
# additive shine, light bodies a dark shadow (see build_grooves_overlay).
VINYL_GROOVE_COLORS = {
    # Light bodies — dark shadow haze (subtle)
    'cream':      (0, 0, 0, 7),
    'mono':       (0, 0, 0, 4),
    'fire':       (0, 0, 0, 9),
    'gold':       (0, 0, 0, 9),
    'ocean':      (0, 0, 0, 9),
    'emerald':    (0, 0, 0, 9),
    'lavender':   (0, 0, 0, 9),
    'purple':     (0, 0, 0, 10),
    'rose':       (0, 0, 0, 9),
    'copper':     (0, 0, 0, 9),
    'rust':       (0, 0, 0, 10),
    'cyan':       (0, 0, 0, 9),
    'sea-foam':   (0, 0, 0, 8),   # mid-light body — subtle shadow grooves
    # Dark bodies — light additive shine
    'red':        (255, 255, 255, 35),
    'navy':       (255, 255, 255, 35),
    'forest':     (255, 255, 255, 35),
    'plum':       (255, 255, 255, 35),
    'chocolate':  (255, 255, 255, 35),
    'slate':      (255, 255, 255, 25),
    'amber':      (255, 255, 255, 35),
    'teal':       (255, 255, 255, 35),
    'burgundy':   (255, 255, 255, 35),
    'olive':      (255, 255, 255, 35),
    'midnight':   (255, 255, 255, 35),
}

# Clear vinyl's groove haze, as rgba (additive).
CLEAR_GROOVE_COLOR = (255, 255, 255, 55)

# Mandelbrot color schemes: (interior, r_params, g_params, b_params)
# Each channel: (base, amplitude, frequency, phase)
MANDELBROT_COLORS = {
    'purple':    ((15, 5, 30),   (40, 180, 12.0, 0.0), (20, 80, 8.0, 2.0), (80, 175, 10.0, 4.0)),
    'fire':      ((30, 5, 0),    (80, 175, 10.0, 0.0), (20, 160, 8.0, 1.5), (5, 40, 6.0, 3.0)),
    'ocean':     ((5, 10, 30),   (10, 60, 6.0, 1.0),  (40, 140, 8.0, 0.5), (60, 195, 10.0, 0.0)),
    'emerald':   ((5, 20, 10),   (20, 80, 8.0, 2.0),  (50, 180, 10.0, 0.0), (15, 70, 6.0, 1.5)),
    'gold':      ((25, 15, 5),   (80, 175, 10.0, 0.0), (50, 150, 9.0, 0.5), (10, 50, 6.0, 2.0)),
    'mono':      ((10, 10, 10),  (30, 225, 10.0, 0.0), (30, 225, 10.0, 0.0), (30, 225, 10.0, 0.0)),
    'copper':    ((25, 12, 5),   (60, 150, 9.0, 0.5),  (30, 100, 7.0, 1.0), (10, 60, 5.0, 2.5)),
    'teal':      ((5, 15, 20),   (10, 50, 6.0, 1.5),  (40, 150, 9.0, 0.0), (50, 160, 8.0, 0.5)),
    'rose':      ((25, 8, 15),   (60, 140, 8.0, 0.0),  (20, 70, 6.0, 2.0), (40, 120, 9.0, 1.0)),
    'rust':      ((30, 8, 5),    (70, 140, 8.0, 0.0),  (25, 80, 6.0, 1.0), (10, 45, 5.0, 2.5)),
    'lavender':  ((18, 10, 25),  (50, 130, 10.0, 1.0), (30, 90, 7.0, 2.5), (60, 160, 9.0, 0.0)),
    'midnight':  ((5, 5, 20),    (15, 60, 7.0, 2.0),  (10, 50, 6.0, 1.0), (40, 170, 10.0, 0.0)),
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

# Groove haze colour per munafo variant, as rgba, keyed on config name.
# Dark grooves (normal alpha) on light fields read as shadow; light grooves
# (additive) on dark fields read as shine. A red channel above 128 switches
# build_grooves_overlay to additive blending.
MUNAFO_GROOVE_COLORS = {
    'deep5_v1': (0, 0, 0, 32),   # peach field — dark grooves
    'deep6_v1': (0, 0, 0, 30),   # bright yellow outer — dark
    'deep7_v1': (0, 0, 0, 28),   # magenta/coral mid — dark
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

# Background / spindle-hole colour (also lp.display window bg).
DARK_BG = (17, 17, 17)


# Vinyl Effects: finishes applied over any style (lpcore/vinyl/effects.py).
# id -> display label, in the order they apply.
VINYL_EFFECTS = {
    'glass': 'Glass',
    'deep-edge': 'Deep edge',
    'rim-light': 'Rim light',
}


# Groove treatments: how the music-zone grooves catch the light, chosen per
# record next to the Vinyl Effects. 'auto' keeps each style's own grooves.
GROOVE_TREATMENTS = {
    'auto': 'Auto',
    'shine': 'Shine',
    'shadow': 'Shadow',
    'smooth': 'Smooth',
}
GROOVE_SHINE = (255, 255, 255, 45)     # additive
GROOVE_SHADOW = (0, 0, 0, 30)          # normal alpha

# Auto grooves for a colour with no VINYL_GROOVE_COLORS entry (a new or
# user-made colour): bodies brighter than this luma (0-255) get a dark haze,
# darker ones a light shine. 115 sits between the brightest built-in shine body
# (amber, 100) and the darkest shadow body (rust, 131), so the rule agrees with
# every entry in the table.
GROOVE_AUTO_LUMA_SPLIT = 115
AUTO_LIGHT_BODY_GROOVE = (0, 0, 0, 9)
AUTO_DARK_BODY_GROOVE = (255, 255, 255, 35)
