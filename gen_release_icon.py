#!/usr/bin/env python
"""Render the release icon: Crucible & Ruin on the teal-marble vinyl, fully shaded.

Reuses the real render path (build_record + grooves + shine) so the icon matches
what the app actually draws: the teal-marble disc, the album-art label, the
music-zone grooves laid out from Crucible & Ruin's real track lengths, and the
fixed specular shine. Headless: builds plain pygame Surfaces and composites
them, no SDL window/renderer needed.

    python gen_release_icon.py            # writes static/release-crucible-and-ruin.png

Re-run to regenerate after a render tweak.
"""
import os
import threading

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import numpy as np
import pygame
from mutagen import File as MutagenFile

from lp.display import Display
from lpcore.covers import find_cover
from lpcore.tracks import album_track_paths
from lpcore.vinyl.catalog import RECORD_SUPERSAMPLE
from lpcore.vinyl.settings import VinylSettings

HERE = os.path.dirname(os.path.abspath(__file__))
ALBUM_DIR = '/mnt/share/media/Music/Howling Giant/2025 - Crucible & Ruin'
OUT = os.path.join(HERE, 'static', 'release-crucible-and-ruin.png')

# Internal render radius (high-res); the disc surface is 2x this. Downscaled at
# the end for a crisp icon.
RENDER_R = 512
ICON_R = 320  # final disc radius (icon is 2*ICON_R square)

ARTIST, ALBUM = 'HOWLING GIANT', 'CRUCIBLE & RUIN'


class IconPlayer:
    """Minimal player surface the Display render helpers read from."""
    def __init__(self):
        self.album_path = ALBUM_DIR
        self._lock = threading.Lock()

    def on(self, event, cb):
        pass


# The release look: teal-marble with the album art as the label.
ICON_SETTINGS = VinylSettings(style='nebula-teal-marble', label='art',
                              label_text='curved', label_font='georgia')


def real_boundaries():
    """Track-start offsets (seconds), so the music-zone gaps land on the real
    track boundaries."""
    bounds, cumulative = [], 0.0
    for path in album_track_paths(ALBUM_DIR):
        bounds.append(cumulative)
        cumulative += MutagenFile(path).info.length
    return bounds, cumulative


def add_like_the_display(base, overlay):
    """Additive blend the way the display's SDL textures do it (BLENDMODE_ADD):
    the overlay's colour is weighted by its alpha before it's added. pygame's
    BLEND_RGBA_ADD adds the colour unweighted, which washes the music zone out
    and leaves the track gaps as dark rings."""
    alpha = pygame.surfarray.array_alpha(overlay).astype(np.float32)[..., None] / 255.0
    weighted = (pygame.surfarray.array3d(overlay).astype(np.float32) * alpha).astype(np.uint8)
    light = pygame.Surface(overlay.get_size())
    pygame.surfarray.blit_array(light, weighted)
    base.blit(light, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def main():
    pygame.init()
    player = IconPlayer()
    config = {'display': {'width': 1080, 'height': 1080, 'fullscreen': False}}
    disp = Display(config, player, settings=ICON_SETTINGS)
    disp.width = disp.height = 1080
    disp._load_fonts()

    boundaries, album_dur = real_boundaries()
    art = find_cover(ALBUM_DIR)
    style = disp.vinyl.get_vinyl_style(ALBUM_DIR)

    # Body (supersampled), grooves, shine: exactly as the live display builds them.
    body = disp.vinyl.build_record(RENDER_R * RECORD_SUPERSAMPLE, boundaries, album_dur,
                                   art, ALBUM_DIR, ARTIST, ALBUM)
    grooves, blend = disp.vinyl.build_grooves_overlay(RENDER_R, style, boundaries, album_dur)
    shine = disp.vinyl.build_shine_overlay(RENDER_R, style)

    d = RENDER_R * 2
    base = pygame.transform.smoothscale(body, (d, d))
    if blend == 'add':
        add_like_the_display(base, grooves)
    else:
        base.blit(grooves, (0, 0))
    base.blit(shine, (0, 0))

    out = pygame.transform.smoothscale(base, (ICON_R * 2, ICON_R * 2))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pygame.image.save(out, OUT)
    print(f'wrote {OUT} ({ICON_R * 2}x{ICON_R * 2}, {len(boundaries)} tracks)')


if __name__ == '__main__':
    main()
