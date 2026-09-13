"""Vinyl Effects: finishes for the plastic, applied on top of any style.

A style decides the pattern; an effect decides the material it is pressed
into. Effects never look at the pattern, so they work on every style. They
depend only on distance from the centre, so they look the same at every angle
and stay put as the record spins under the fixed shine. They are a few array
operations on the finished disc, cheap enough to apply whenever a record is
drawn, so a cached style image never needs re-rendering for an effect.

Clear vinyl carries its own lighting and takes no effects (see build_record).
"""
from functools import lru_cache

import numpy as np
import pygame

from .catalog import VINYL_EFFECTS

# Glass: tinted plastic over a pale surface, which lifts the colour slightly
# and cools it, the way light behind a pane does.
GLASS = dict(amount=0.55, behind=(205, 210, 214), gain=1.45)
# Deep edge: the colour gets darker and richer towards the rim, where light
# travels through more plastic. `start` is the radius (0 centre, 1 rim) it
# begins at.
DEEP_EDGE = dict(start=0.72, depth=0.30)
# Rim light: a thin soft highlight where light pipes out of the edge. `width`
# is a fraction of the radius.
RIM_LIGHT = dict(width=0.006, strength=0.35)


def normalize_effects(effects):
    """Known effect ids, deduplicated, in the order they apply.

    Raises ValueError for anything that isn't a list of known ids.
    """
    if isinstance(effects, str) or not isinstance(effects, (list, tuple)):
        raise ValueError(f"effects must be a list of {list(VINYL_EFFECTS)}, got {effects!r}")
    unknown = [e for e in effects if e not in VINYL_EFFECTS]
    if unknown:
        raise ValueError(f"unknown vinyl effects {unknown}; known: {list(VINYL_EFFECTS)}")
    return [e for e in VINYL_EFFECTS if e in effects]


@lru_cache(maxsize=8)
def _radius(size):
    """Distance from the disc centre as a fraction of the radius, per pixel.
    Symmetric in x and y, so it indexes a surfarray the same either way round."""
    d = size * 2
    yy, xx = np.mgrid[0:d, 0:d].astype(np.float32)
    return np.hypot(xx + 0.5 - size, yy + 0.5 - size) / size


def apply_effects(surf, effects):
    """Apply `effects` to a square disc surface in place."""
    effects = normalize_effects(effects)
    if not effects:
        return
    size = surf.get_width() // 2
    rn = _radius(size)
    pixels = pygame.surfarray.pixels3d(surf)
    col = pixels.astype(np.float32)
    if 'glass' in effects:
        a, gain = GLASS['amount'], GLASS['gain']
        behind = np.asarray(GLASS['behind'], dtype=np.float32) / 255.0
        col *= (1.0 - a) + a * gain * behind
    if 'deep-edge' in effects:
        start = DEEP_EDGE['start']
        ramp = np.clip((rn - start) / (1.0 - start), 0.0, 1.0) ** 2
        col *= (1.0 - DEEP_EDGE['depth'] * ramp)[..., None]
    if 'rim-light' in effects:
        glow = np.exp(-((1.0 - rn) / RIM_LIGHT['width']) ** 2) * RIM_LIGHT['strength']
        col += (255.0 - col) * glow[..., None]
    pixels[...] = np.clip(col, 0, 255).astype(np.uint8)
    del pixels     # release the surface lock
