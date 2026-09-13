"""Headless screenshot harness for the kiosk display: the lp-side twin of
`lpdeck.shot`.

Renders the REAL `Display._render_playing` to a PNG with no display attached and
no player running, driven by a fake now-playing status. The point is to be able
to look at a layout change without deploying to the kiosk and interrupting an
album: the SDL2 renderer works fine under the dummy video driver, including
`to_surface()` readback.

    python -m lp.shot out.png
    python -m lp.shot out.png --title "A Very Long Song Title That Will Not Fit"
    python -m lp.shot out.png --track 7 --of 12 --size 1920x1080 --art cover.jpg
    python -m lp.shot out.png --style nebula-marble --label art

The album art defaults to a generated placeholder, so the harness needs nothing
from a real library. `--art` takes a real cover when you want to eyeball
contrast against actual artwork.
"""
import argparse
import os
import sys
import threading

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
from pygame._sdl2 import video as sdl2_video

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lp.display import Display
from lpcore.vinyl.settings import VinylSettings


class _FakePlayer:
    """The slice of PlayerBackend that _render_playing actually touches."""

    def __init__(self, art_path, album_path):
        self._lock = threading.Lock()
        self.album_path = album_path
        self._art_path = art_path

    def on(self, _event, _callback):
        pass

    def get_current_song_info(self):
        return self._art_path, None


def _placeholder_art(path, size=720):
    """A generated cover, so the harness depends on no real library."""
    surf = pygame.Surface((size, size))
    for y in range(size):
        t = y / float(size - 1)
        surf.fill((int(120 - 70 * t), int(60 + 40 * t), int(150 - 60 * t)),
                  pygame.Rect(0, y, size, 1))
    pygame.image.save(surf, path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out', help='PNG path to write')
    ap.add_argument('--artist', default='Pallbearer')
    ap.add_argument('--album', default='Forgotten Days')
    ap.add_argument('--date', default='2020-10-23')
    ap.add_argument('--title', default='Rite of Ruin', help='track title')
    ap.add_argument('--track', type=int, default=3, help='track number')
    ap.add_argument('--of', type=int, default=11, help='total tracks')
    ap.add_argument('--size', default='1920x1080', help='render resolution, WxH')
    ap.add_argument('--art', default=None, help='cover image (default: generated)')
    ap.add_argument('--elapsed', type=float, default=0.42,
                    help='fraction of the album played, for needle position')
    ap.add_argument('--style', default=VinylSettings.style,
                    help='vinyl style id, as the web picker sends (e.g. nebula-marble)')
    ap.add_argument('--label', default=VinylSettings.label,
                    help='label id (e.g. art, label-white, color-cyan)')
    ap.add_argument('--effects', default='',
                    help='comma-separated Vinyl Effects (e.g. glass,rim-light)')
    ap.add_argument('--grooves', default='auto',
                    help='groove treatment: auto, shine, shadow or smooth')
    args = ap.parse_args(argv)

    width, height = (int(v) for v in args.size.lower().split('x'))

    os.environ.setdefault('SDL_HINT_RENDER_SCALE_QUALITY', '2')
    pygame.init()

    art = args.art
    if art is None:
        art = _placeholder_art(os.path.join(os.path.dirname(os.path.abspath(args.out)),
                                            '_shot_art.png'))

    config = {'display': {'width': width, 'height': height, 'fullscreen': False}}
    settings = VinylSettings(style=args.style, label=args.label).update(
        effects=[e for e in args.effects.split(',') if e], grooves=args.grooves)
    # A non-empty album path is required: VinylRenderer.get_vinyl_style()
    # resolves no style for a falsy path and the disc silently renders black.
    display = Display(config, _FakePlayer(art, '/lp-shot/album'), port=0,
                      settings=settings)

    display.window = sdl2_video.Window('lp-shot', size=(width, height), hidden=True)
    display.renderer = sdl2_video.Renderer(display.window, accelerated=0)
    display.renderer.logical_size = (width, height)
    display._load_fonts()
    display._build_needle_texture()

    album_duration = 45 * 60.0
    boundaries = [album_duration * i / args.of for i in range(args.of)]
    status = {
        'playing': True,
        'artist': args.artist,
        'album': args.album,
        'track_title': args.title,
        'track_number': args.track,
        'total_tracks': args.of,
        'date': args.date,
        'progress': {
            'album_duration': album_duration,
            'elapsed': album_duration * args.elapsed,
            'track_boundaries': boundaries,
        },
    }

    display._render_playing(status)
    display.renderer.present()
    pygame.image.save(display.renderer.to_surface(), args.out)
    print(f'wrote {args.out}  ({width}x{height})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
