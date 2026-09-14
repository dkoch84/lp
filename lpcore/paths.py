"""Where lp keeps things that must outlive a checkout.

A git checkout keeps everything next to the code: the vinyl cache under
``lpcore/cache/``, and the small state files (the remembered port, favorites,
the Last.fm session) at the repo root. That is the right default for
development and it is what every existing install has.

A release install (see ``lp.update``) unpacks each release into its own folder
and swaps a ``current`` symlink, so anything stored next to the code would be
lost on the first update. Two environment variables move those things out:

    LP_DATA_DIR    state files: .lp_state.json, .lp_launch.json, .lastfm_*
    LP_CACHE_DIR   the rendered vinyl images (mandelbrot/, nebula/, munafo/)
                   and the thumbnail cache

Both default to their in-checkout locations, so a plain ``python main.py``
behaves exactly as before.
"""
import os

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_dir():
    """The checkout (or unpacked release) this code runs from."""
    return _REPO


def data_dir():
    """Folder for small per-install state files. Created on demand."""
    path = os.environ.get('LP_DATA_DIR') or _REPO
    os.makedirs(path, exist_ok=True)
    return path


def cache_dir():
    """Root of the rendered-image caches (``<cache>/nebula/teal-marble.png``)."""
    return os.environ.get('LP_CACHE_DIR') or os.path.join(_REPO, 'lpcore', 'cache')


def data_file(name):
    return os.path.join(data_dir(), name)
