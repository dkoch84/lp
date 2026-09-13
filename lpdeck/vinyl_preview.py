"""Static vinyl swatches for the override chooser (req #7 UI).

Renders a small, art-less vinyl disc for a (style, label) pair so the picker
shows *what you're choosing*. Reuses lpcore's VinylRenderer and the shared
`composite_disc` (so grooves blend exactly like lp's display). pygame isn't
thread-safe and the image provider runs on scene-graph worker threads, so all
rendering is serialised behind the lock the playing record also takes;
results are disk-cached.
"""
from lpcore.vinyl.render import VinylRenderer
from lpcore.vinyl.settings import VinylSettings
from .vinyl_item import RENDER_LOCK as _LOCK, _ensure_pygame, composite_disc
_BOUNDS = [0, 80, 160, 240]      # a few fake tracks so grooves have gaps
_DUR = 240.0


def preview(style, label, size, art_path=None):
    """A disc QImage for (style, label) at `size`×`size` px. `art_path` is the
    cover shown by the picture disc and the album-art label; without it they
    fall back to a plain black disc and label."""
    _ensure_pygame()
    with _LOCK:
        renderer = VinylRenderer(VinylSettings(style=style, label=label))
        disc, _ = composite_disc(renderer, size, _BOUNDS, _DUR, art_path=art_path,
                                 album_path="preview", artist="", album="",
                                 with_shine=False)
        return disc
