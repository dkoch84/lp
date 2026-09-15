"""Fractal & nebula vinyl generation, plus the per-album style picker.

Pure rendering functions (no Display/Qt dependency): they generate mandelbrot,
nebula, julia and munafo vinyl/label surfaces (caching the results as PNGs), and
_pick_vinyl_style maps an album + override to a concrete style. Shared by lp's
display and lp-deck via lpcore.
"""
import os
import random

import numpy as np
import pygame

from lpcore.vinyl.catalog import (
    JULIA_VARIANTS, MANDELBROT_COLORS, MANDELBROT_VARIANTS, MANDELBROT_ZOOMS,
    MUNAFO_VARIANTS, PRERENDER_SIZE, STYLE_DISTRIBUTION, VINYL_COLORS)
from lpcore.vinyl import styles
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

# Defaults for the layered-smoke renderer (lp-studio's "smoke" family). A variant
# overrides any of them with a dict as its 8th tuple element.
SMOKE_MAX_LAYERS = 12
SMOKE_LAYER_PARAMS = dict(
    layers=6,              # overlapping smoke layers, each pointing its own way
    opacity=0.60,          # darkness of one layer's densest smoke
    amount=0.22,           # how much of the field turns to smoke (vein threshold)
    gamma=1.6,             # falloff from a wisp's core to its edge
    soft=2,                # edge softening as a resolution divisor; 1 = none
    stretch=(1.6, 3.2),    # per-layer elongation along its direction, min and max
    warp_oct=5, arm_oct=6, # the marble field's warp and detail octaves
    deep_soft=1,           # alternate layers softened as if deeper; 1 = off
    deep_opacity=0.5,      # and dimmed by this factor
    veil_soft=1,           # softening of the lighter body veil; 1 = none
    light=(68, 150, 140), mid=(48, 112, 104), ink=(16, 40, 34),
    opacity_variation=1.0, # how much layer darkness varies around `opacity`; 0 = all equal
    spread=1.0,            # how widely layer directions fan out; 0 = all one way
    rotate=0.0,            # degrees added to every layer's direction
    # Per-layer trims, index 0 = the first layer. The defaults leave each layer
    # exactly as generated; layers past the end of a tuple are untrimmed.
    layer_opacity=(1.0,) * SMOKE_MAX_LAYERS,   # multiplies that layer's opacity
    layer_amount=(1.0,) * SMOKE_MAX_LAYERS,    # multiplies how much of it is smoke
    layer_stretch=(1.0,) * SMOKE_MAX_LAYERS,   # multiplies its stretch
    layer_angle=(0.0,) * SMOKE_MAX_LAYERS,     # degrees added to its direction
    layer_soft=(0,) * SMOKE_MAX_LAYERS,        # extra softening on top of the global
    # Dark accents: a few extra, darker layers laid over the finished smoke from
    # their own random stream, so adding them never moves the layers above.
    # accents=0 switches the pass off entirely.
    accents=0,
    accent_seed=0,               # picks a different set of accents
    accent_amount=0.12,          # how much of each accent layer is dark; low = thin threads
    accent_opacity=0.85,
    accent_gamma=1.6,
    accent_soft=1,               # 1 = sharp, higher = soft dark clouds
    accent_stretch=(2.0, 4.0),
    accent_follow=0.6,           # 0 = anywhere, 1 = only where smoke already is
    accent_ink=(6, 18, 15),
    # Smoke shadow: the smoke casts a soft shadow on the plastic beneath it,
    # darkening the clear areas next to it. 0 switches it off.
    shadow=0.0,
    shadow_soft=12,              # how far the shadow spreads (1 = hard)
)


def _soften_field(field, factor):
    """Resolution-relative softening: shrink by `factor`, scale back up."""
    factor = int(factor)
    if factor <= 1:
        return field
    d = field.shape[0]
    surf = pygame.Surface((d, d))
    grey = np.clip(field * 255.0, 0, 255).astype(np.uint8)
    pygame.surfarray.blit_array(surf, np.dstack([grey.T] * 3))
    small = max(1, d // factor)
    surf = pygame.transform.smoothscale(pygame.transform.smoothscale(surf, (small, small)), (d, d))
    return pygame.surfarray.array3d(surf)[..., 0].T.astype(np.float64) / 255.0


# Optional memo for _marble_blend. Computing these fields is nearly all of a
# smoke render, yet most tuning (colours, opacity, amount, softness) reuses the
# same fields, so lp-studio's render worker turns this on and those changes
# become near-instant. It stays off by default: the kiosk renders each style
# once, and holding full-size fields would only cost it memory.
_FIELD_CACHE = None          # OrderedDict of key -> read-only field, when enabled
_FIELD_CACHE_LIMIT = 0
_FIELD_CACHE_BYTES = 0


def enable_field_cache(max_bytes=384 * 2**20):
    """Keep recently computed smoke fields, up to `max_bytes`, oldest evicted first."""
    global _FIELD_CACHE, _FIELD_CACHE_LIMIT, _FIELD_CACHE_BYTES
    from collections import OrderedDict
    if _FIELD_CACHE is None:
        _FIELD_CACHE, _FIELD_CACHE_BYTES = OrderedDict(), 0
    _FIELD_CACHE_LIMIT = int(max_bytes)


def disable_field_cache():
    global _FIELD_CACHE, _FIELD_CACHE_LIMIT, _FIELD_CACHE_BYTES
    _FIELD_CACHE, _FIELD_CACHE_LIMIT, _FIELD_CACHE_BYTES = None, 0, 0


def _marble_blend(seed, size, px, py, angle_deg, stretch, warp_oct, arm_oct, offset):
    """The marble (nebula swirl) field with its two-armed swirl off, sampled on
    coordinates rotated to `angle_deg` and stretched along that direction, so one
    layer's wisps all lean one way."""
    global _FIELD_CACHE_BYTES
    if _FIELD_CACHE is None:
        return _marble_blend_compute(seed, size, px, py, angle_deg, stretch, warp_oct, arm_oct, offset)
    # px/py are always the full mgrid for `size`, so size stands in for them.
    key = (seed, size, float(angle_deg), float(stretch), warp_oct, arm_oct, float(offset))
    field = _FIELD_CACHE.get(key)
    if field is not None:
        _FIELD_CACHE.move_to_end(key)
        return field
    field = _marble_blend_compute(seed, size, px, py, angle_deg, stretch, warp_oct, arm_oct, offset)
    field.flags.writeable = False     # shared between renders: nobody may edit it in place
    _FIELD_CACHE[key] = field
    _FIELD_CACHE_BYTES += field.nbytes
    while _FIELD_CACHE_BYTES > _FIELD_CACHE_LIMIT and len(_FIELD_CACHE) > 1:
        _old_key, old = _FIELD_CACHE.popitem(last=False)
        _FIELD_CACHE_BYTES -= old.nbytes
    return field


def _marble_blend_compute(seed, size, px, py, angle_deg, stretch, warp_oct, arm_oct, offset):
    grids = _make_nebula_grids(seed)
    dx = px - size
    dy = py - size
    a = np.deg2rad(angle_deg)
    xr = (dx * np.cos(a) + dy * np.sin(a)) / stretch
    yr = -dx * np.sin(a) + dy * np.cos(a)
    nx = (xr + size) / size * 3.0 + offset
    ny = (yr + size) / size * 3.0 + offset * 0.6
    wx = nx + _fbm(nx + 1.7, ny + 9.2, warp_oct, 0, grids) * 3.0
    wy = ny + _fbm(nx + 8.3, ny + 2.8, warp_oct, 2, grids) * 3.0
    wx2 = wx + _fbm(wx * 0.8 + 3.1, wy * 0.8 + 7.7, max(warp_oct - 1, 2), 4, grids) * 2.0
    wy2 = wy + _fbm(wx * 0.8 + 1.3, wy * 0.8 + 4.9, max(warp_oct - 1, 2), 6, grids) * 2.0
    arm = _fbm(wx2, wy2, arm_oct, 1, grids)
    return _smoothstep(np.clip((arm - 0.3) * 2.5, 0.0, 1.0))


def _render_smoke_layers_surface(variant, size):
    """Translucent vinyl with smoke running in every direction.

    Several layers of the marble field, each with its own seed, direction and
    stretch, are stacked by transmittance: every layer lets through a share of
    the light, so where wisps cross the smoke gets darker, as it does in a real
    smoke pressing. Alternate layers can be softened and dimmed to sit deeper in
    the plastic. The body underneath is a lighter veil from one more field.
    """
    seed = variant[0]
    P = {**SMOKE_LAYER_PARAMS, **(variant[7] if len(variant) > 7 else {})}
    rng = np.random.default_rng(seed)
    n_layers = max(1, int(P['layers']))
    angles = rng.uniform(0, 180, n_layers)
    d = size * 2
    py, px = np.mgrid[0:d, 0:d].astype(np.float64)
    lo, hi = P['stretch']
    amount = max(float(P['amount']), 1e-3)
    warp_oct, arm_oct = int(P['warp_oct']), int(P['arm_oct'])

    def trim(key, i, untouched):
        seq = P[key]
        return seq[i] if i < len(seq) else untouched

    spread, rotate = float(P['spread']), float(P['rotate'])
    variation = float(P['opacity_variation'])
    transmit = np.ones((d, d))
    for i in range(n_layers):
        # The random draws happen in the same order whatever the trims are, so
        # changing one layer never reshuffles the others. The global transforms
        # are only applied when moved off their defaults, which keeps an
        # untouched style byte-identical to before they existed.
        angle = angles[i]
        if spread != 1.0 or rotate != 0.0:
            angle = 90.0 + (angle - 90.0) * spread + rotate
        angle = angle + trim('layer_angle', i, 0.0)
        stretch = rng.uniform(lo, hi) * trim('layer_stretch', i, 1.0)
        layer_amount = max(amount * trim('layer_amount', i, 1.0), 1e-3)
        blend = _marble_blend(seed + 13 * i, size, px, py, angle, stretch,
                              warp_oct, arm_oct, i * 4.1)
        dens = np.clip((layer_amount - blend) / layer_amount, 0.0, 1.0) ** P['gamma']
        wobble = rng.uniform(0.75, 1.15)
        if variation != 1.0:
            wobble = 1.0 + (wobble - 1.0) * variation
        opacity = P['opacity'] * wobble * trim('layer_opacity', i, 1.0)
        extra_soft = int(trim('layer_soft', i, 0))
        if int(P['deep_soft']) > 1 and i % 2:
            dens = _soften_field(dens, int(P['deep_soft']) + extra_soft)
            opacity *= P['deep_opacity']
        else:
            dens = _soften_field(dens, int(P['soft']) + extra_soft)
        transmit *= 1.0 - np.clip(opacity * dens, 0.0, 1.0)

    veil = _marble_blend(seed + 997, size, px, py, rng.uniform(0, 180), 1.5,
                         warp_oct, arm_oct, 33.0)
    veil = _soften_field(veil, P['veil_soft'])
    light, mid, ink = [np.asarray(c, dtype=np.float64) for c in (P['light'], P['mid'], P['ink'])]
    body = mid[None, None, :] + (light - mid)[None, None, :] * veil[..., None]
    smoke = (1.0 - transmit)[..., None]
    col = body * (1.0 - smoke) + ink[None, None, :] * smoke

    if float(P['shadow']) > 0.0:
        cover = smoke[..., 0]
        cast = _soften_field(cover, int(P['shadow_soft']))
        col = col * (1.0 - float(P['shadow']) * cast * (1.0 - cover))[..., None]

    if int(P['accents']) > 0:
        col = _apply_dark_accents(col, smoke[..., 0], P, seed, size, px, py, warp_oct, arm_oct)

    r = np.hypot(px + 0.5 - size, py + 0.5 - size) / size
    alpha = np.clip((1.0 - r) * size + 0.5, 0.0, 1.0)
    rgba = np.dstack([np.clip(col, 0, 255), alpha * 255]).astype(np.uint8)
    return pygame.image.frombuffer(np.ascontiguousarray(rgba).tobytes(), (d, d), 'RGBA').copy()


def _apply_dark_accents(col, smoke, P, seed, size, px, py, warp_oct, arm_oct):
    """Lay darker smoke over a finished layered-smoke body.

    Accent layers are marble fields like the main layers, but drawn from their
    own generator, darkened towards ``accent_ink``, and optionally kept to
    where smoke already is (``accent_follow``) so they deepen the existing
    wisps instead of starting new ones in clear plastic.
    """
    arng = np.random.default_rng([seed, 7771, int(P['accent_seed'])])
    lo, hi = sorted(P['accent_stretch'])
    amount = max(float(P['accent_amount']), 1e-3)
    transmit = np.ones_like(smoke)
    for j in range(int(P['accents'])):
        blend = _marble_blend(seed + 5003 + 13 * j + 101 * int(P['accent_seed']), size, px, py,
                              arng.uniform(0, 180), arng.uniform(lo, hi),
                              warp_oct, arm_oct, 57.0 + j * 4.1)
        dens = np.clip((amount - blend) / amount, 0.0, 1.0) ** P['accent_gamma']
        dens = _soften_field(dens, int(P['accent_soft']))
        opacity = P['accent_opacity'] * arng.uniform(0.8, 1.1)
        transmit *= 1.0 - np.clip(opacity * dens, 0.0, 1.0)
    acc = 1.0 - transmit
    follow = float(np.clip(P['accent_follow'], 0.0, 1.0))
    if follow > 0.0:
        where = smoke / max(float(smoke.max()), 1e-6)
        acc = acc * ((1.0 - follow) + follow * where)
    ink = np.asarray(P['accent_ink'], dtype=np.float64)
    return col * (1.0 - acc[..., None]) + ink[None, None, :] * acc[..., None]


# Modulator fields a parameterized nebula channel can ride on. Each maps the
# renderer's noise fields (t1/t2/t3, hue-shift hs) — plus two derived forms — to
# a [0,1]-ish array. 'sin' is the shimmering banded modulator (0.5+0.5·sin).
NEBULA_MODS = ('t1', 't2', 't3', 'hs', 'inv_t3', 'sin')


def _nebula_mod(name, t1, t2, t3, hs, sin_freq):
    if name == 't2':
        return t2
    if name == 't3':
        return t3
    if name == 'hs':
        return hs
    if name == 'inv_t3':
        return 1.0 - t3
    if name == 'sin':
        return 0.5 + 0.5 * np.sin(t1 * sin_freq)
    return t1


def _nebula_palette(col1, col2, amp1, amp2,
                    mods1=('t1', 'hs', 'sin'), mods2=('t3', 't1', 'inv_t3'),
                    sin_freq=8.0, bright='std', sparkle='none'):
    """Build a nebula palette function from numeric params — the generic form of
    the hand-written ``_nebula_*`` palettes (same template as ``_clouds_palette``
    is for clouds). Two colours (``col1``/``col2`` = per-channel base, ``amp1``/
    ``amp2`` = per-channel modulation depth) blended by ``blend``; each channel
    rides one of NEBULA_MODS. ``bright`` ∈ {std, galaxy (br²), pastel (0.4+0.6·br)};
    ``sparkle`` ∈ {none, stars, pop} adds the galaxy/oil-spill highlight term.
    """
    c1, c2 = [float(x) for x in col1], [float(x) for x in col2]
    a1, a2 = [float(x) for x in amp1], [float(x) for x in amp2]

    def fn(br, blend, t1, t2, t3, hs):
        if bright == 'galaxy':
            b = br * br
        elif bright == 'pastel':
            b = 0.4 + 0.6 * br
        else:
            b = br
        f1 = [_nebula_mod(m, t1, t2, t3, hs, sin_freq) for m in mods1]
        f2 = [_nebula_mod(m, t1, t2, t3, hs, sin_freq) for m in mods2]
        ch1 = [b * (c1[i] + a1[i] * f1[i]) for i in range(3)]
        ch2 = [b * (c2[i] + a2[i] * f2[i]) for i in range(3)]
        r = ch1[0] * blend + ch2[0] * (1 - blend)
        g = ch1[1] * blend + ch2[1] * (1 - blend)
        bl = ch1[2] * blend + ch2[2] * (1 - blend)
        if sparkle == 'stars':
            s = np.maximum(0, t1 * t2 * 4 - 1.2) ** 2
            r, g, bl = r + s * 200, g + s * 180, bl + s * 255
        elif sparkle == 'pop':
            pop = np.maximum(0, t1 * t2 * 3 - 0.9)
            r, g, bl = r + pop * 80, g + pop * 100, bl + pop * 90
        return (r, g, bl)

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

def _variants_from_files():
    """NEBULA_VARIANTS entries for the style files lp-studio ships (see
    lpcore.vinyl.styles), in the tuple shapes the hand-written entries use."""
    variants = []
    for entry in styles.load('nebula'):
        name, seed, p = entry['name'], entry['seed'], styles.to_tuples(entry['params'])
        if entry['family'] == 'smoke':
            variants.append((seed, None, name, 1.0, 5, 6, 'layers', p))
        elif entry['family'] == 'clouds':
            variants.append((seed, _clouds_palette(p['cloud'], p['sky']), name,
                             p['saturation'], 6, 7, 'clouds'))
        else:
            palette = _nebula_palette(p['col1'], p['col2'], p['amp1'], p['amp2'],
                                      mods1=p['mods1'], mods2=p['mods2'], sin_freq=p['sin_freq'],
                                      bright=p['bright'], sparkle=p['sparkle'])
            variants.append((seed, palette, name, p['saturation'], p['warp'], p['arm']))
    return variants


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
    # Styles made in lp-studio live as data files (lpcore/vinyl/styles/nebula),
    # in their own `order`: teal-marble, purple-marble, pink-marble, then the
    # other marbles built from teal's brightness ramp.
    *_variants_from_files(),
    (42, _nebula_galaxy,       'galaxy',         1.6, 6, 7),
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
    if len(variant) > 6 and variant[6] == 'layers':
        return _render_smoke_layers_surface(variant, size)
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
    base_dark, r_p, g_p, b_p = scheme

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
