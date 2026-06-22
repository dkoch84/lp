"""Filesystem locations for the pre-rendered vinyl caches.

The fractal vinyl bodies/labels (mandelbrot, nebula, julia, munafo) are
expensive to generate, so they're rendered once and cached as PNGs under
``lpcore/cache/``. Both the renderer (read/write) and the web API's preview
endpoint (read) resolve their paths from here.
"""
import os

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # …/lpcore
_REPO = os.path.dirname(_PKG)                                        # repo root

CACHE_DIR = os.path.join(_PKG, 'cache', 'mandelbrot')
NEBULA_CACHE_DIR = os.path.join(_PKG, 'cache', 'nebula')
JULIA_CACHE_DIR = os.path.join(_PKG, 'cache', 'julia')
MUNAFO_CACHE_DIR = os.path.join(_PKG, 'cache', 'munafo')

# The 9000×9000 gold archives live in the sibling `bongsweat` repo. This path is
# only used by prerender_all() to regenerate the vinyl cache; at runtime, lp
# reads the downsampled snapshots from MUNAFO_CACHE_DIR.
MUNAFO_SOURCE_DIR = os.path.join(os.path.dirname(_REPO), 'bongsweat', 'configs')
