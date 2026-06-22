#!/usr/bin/env python
"""Render the release icon: a cyan Diamond Morning vinyl, fully shaded.

Reuses the real render path from lp.display (_build_record + grooves + shine)
so the icon matches what the app actually draws — cyan colorway, the album-art
label, the music-zone grooves laid out from Diamond Morning's real track
boundaries, and the fixed specular shine. Headless: builds plain pygame
Surfaces and composites them, no SDL window/renderer needed.

    python gen_release_icon.py            # writes static/release-karmanjakah.png

Re-run to regenerate after a render tweak.
"""
import os
import threading

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
from mutagen.flac import FLAC

from lp.display import Display, RECORD_SUPERSAMPLE
from lpcore.vinyl.settings import VinylSettings

HERE = os.path.dirname(os.path.abspath(__file__))
ALBUM_DIR = '/mnt/share/media/Music/Karmanjakah/2026 - Diamond morning'
OUT = os.path.join(HERE, 'static', 'release-karmanjakah.png')

# Internal render radius (high-res); the disc surface is 2x this. Downscaled at
# the end for a crisp icon.
RENDER_R = 512
ICON_R = 320  # final disc radius (icon is 2*ICON_R square)

ARTIST, ALBUM = 'KARMANJAKAH', 'DIAMOND MORNING'


class IconPlayer:
    """Minimal player surface the Display render helpers read from."""
    def __init__(self):
        self.album_path = ALBUM_DIR
        self._lock = threading.Lock()

    def on(self, event, cb):
        pass


# The cyan Diamond Morning look, as a VinylSettings.
ICON_SETTINGS = VinylSettings(style='color-cyan', label='art',
                              label_text='curved', label_font='georgia')


def real_boundaries():
    """Track-start offsets (seconds) for Diamond Morning, so the music-zone
    gaps land on the real track boundaries."""
    files = sorted(f for f in os.listdir(ALBUM_DIR) if f.lower().endswith('.flac'))
    bounds, cumulative = [], 0.0
    for f in files:
        bounds.append(cumulative)
        cumulative += FLAC(os.path.join(ALBUM_DIR, f)).info.length
    return bounds, cumulative


def main():
    pygame.init()
    player = IconPlayer()
    config = {'display': {'width': 1080, 'height': 1080, 'fullscreen': False}}
    disp = Display(config, player, settings=ICON_SETTINGS)
    disp.width = disp.height = 1080
    disp._load_fonts()

    boundaries, album_dur = real_boundaries()
    cover = os.path.join(ALBUM_DIR, 'cover.jpg')
    art = cover if os.path.isfile(cover) else None
    style = disp._get_vinyl_style(ALBUM_DIR)

    # Body (supersampled), grooves, shine — exactly as the live display builds them.
    body = disp._build_record(RENDER_R * RECORD_SUPERSAMPLE, boundaries, album_dur,
                              art, ALBUM_DIR, ARTIST, ALBUM)
    grooves, blend = disp._build_grooves_overlay(RENDER_R, style, boundaries, album_dur)
    shine = disp._build_shine_overlay(RENDER_R, style)

    d = RENDER_R * 2
    base = pygame.transform.smoothscale(body, (d, d))
    base.blit(grooves, (0, 0),
              special_flags=pygame.BLEND_RGBA_ADD if blend == 'add' else 0)
    base.blit(shine, (0, 0))

    out = pygame.transform.smoothscale(base, (ICON_R * 2, ICON_R * 2))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pygame.image.save(out, OUT)
    print(f'wrote {OUT} ({ICON_R * 2}x{ICON_R * 2}, {len(boundaries)} tracks)')


if __name__ == '__main__':
    main()
