"""Filesystem locations for the pre-rendered vinyl caches.

The fractal vinyl bodies/labels (mandelbrot, nebula, julia, munafo) are
expensive to generate, so they're rendered once and cached as PNGs under
``lpcore/cache/`` (or ``$LP_CACHE_DIR``, see ``lpcore.paths``). Both the renderer (read/write) and the web API's preview
endpoint (read) resolve their paths from here.
"""
import os

from lpcore.paths import cache_dir, repo_dir

_REPO = repo_dir()

# LP_CACHE_DIR moves the whole tree (a release install shares one cache across
# releases); by default it is lpcore/cache/ in the checkout.
CACHE_ROOT = cache_dir()
CACHE_DIR = os.path.join(CACHE_ROOT, 'mandelbrot')
NEBULA_CACHE_DIR = os.path.join(CACHE_ROOT, 'nebula')
JULIA_CACHE_DIR = os.path.join(CACHE_ROOT, 'julia')
MUNAFO_CACHE_DIR = os.path.join(CACHE_ROOT, 'munafo')

# The 9000×9000 gold archives live in the sibling `bongsweat` repo. This path is
# only used by prerender_all() to regenerate the vinyl cache; at runtime, lp
# reads the downsampled snapshots from MUNAFO_CACHE_DIR.
MUNAFO_SOURCE_DIR = os.path.join(os.path.dirname(_REPO), 'bongsweat', 'configs')
