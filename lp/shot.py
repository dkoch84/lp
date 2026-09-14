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
    python -m lp.shot out.png --album-dir "/music/Artist/2025 - Album" --track 3

The album art defaults to a generated placeholder, so the harness needs nothing
from a real library. `--art` takes a real cover when you want to eyeball
contrast against actual artwork. `--album-dir` takes a real album folder: its
tags, track lengths and cover drive the shot, so the grooves and the needle sit
where that album's tracks really are.
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


def _first_tag(tags, key):
    values = tags.get(key) or ['']
    return str(values[0])


def album_info(folder):
    """([{title, artist, album, date, length, path}], cover path) for a real album
    folder. Shared with lp.video, which walks the same tracks in time."""
    from mutagen import File as MutagenFile

    from lpcore.covers import find_cover
    from lpcore.tracks import album_track_paths

    tracks = []
    for path in album_track_paths(folder):
        f = MutagenFile(path, easy=True)
        tags = (f.tags or {}) if f is not None else {}
        tracks.append({
            'title': _first_tag(tags, 'title') or os.path.splitext(os.path.basename(path))[0],
            'artist': _first_tag(tags, 'artist'),
            'album': _first_tag(tags, 'album'),
            'date': _first_tag(tags, 'date'),
            'length': float(f.info.length) if f is not None else 0.0,
            'path': path,
        })
    if not tracks:
        raise SystemExit(f'no audio files in {folder}')
    return tracks, find_cover(folder)


def headless_display(width, height, settings, art, album_dir, title='lp-shot'):
    """A Display with a hidden window and a software renderer, ready for
    ``_render_playing``; ``renderer.to_surface()`` reads frames back."""
    config = {'display': {'width': width, 'height': height, 'fullscreen': False}}
    # A non-empty album path is required: VinylRenderer.get_vinyl_style()
    # resolves no style for a falsy path and the disc silently renders black.
    display = Display(config, _FakePlayer(art, album_dir or '/lp-shot/album'), port=0,
                      settings=settings)
    display.window = sdl2_video.Window(title, size=(width, height), hidden=True)
    display.renderer = sdl2_video.Renderer(display.window, accelerated=0)
    display.renderer.logical_size = (width, height)
    display._load_fonts()
    display._build_needle_texture()
    return display


def add_look_arguments(ap):
    """The vinyl-look options shot and video share, as the web picker sends them."""
    ap.add_argument('--style', default=VinylSettings.style,
                    help='vinyl style id, as the web picker sends (e.g. nebula-marble)')
    ap.add_argument('--label', default=VinylSettings.label,
                    help='label id (e.g. art, label-white, color-cyan)')
    ap.add_argument('--label-text', default=VinylSettings.label_text,
                    help='artist and album on the label: none, curved, straight or blocky')
    ap.add_argument('--effects', default='',
                    help='comma-separated Vinyl Effects (e.g. glass,rim-light)')
    ap.add_argument('--grooves', default='auto',
                    help='groove treatment: auto, shine, shadow or smooth')
    ap.add_argument('--frame-color', default='auto',
                    help="the frame behind everything: auto or #rrggbb")
    ap.add_argument('--panel-color', default='auto',
                    help="the panel beside the art: auto or #rrggbb")


def settings_from_args(args):
    return VinylSettings(style=args.style, label=args.label,
                         label_text=args.label_text).update(
        effects=[e for e in args.effects.split(',') if e], grooves=args.grooves,
        frame_color=args.frame_color, panel_color=args.panel_color)


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
    ap.add_argument('--album-dir', default=None,
                    help="a real album folder: its tags, track lengths and cover")
    ap.add_argument('--elapsed', type=float, default=None,
                    help='fraction of the album played, for needle position')
    add_look_arguments(ap)
    args = ap.parse_args(argv)

    width, height = (int(v) for v in args.size.lower().split('x'))

    os.environ.setdefault('SDL_HINT_RENDER_SCALE_QUALITY', '2')
    pygame.init()

    artist, album, date, title = args.artist, args.album, args.date, args.title
    track, total = args.track, args.of
    album_duration = 45 * 60.0
    boundaries = [album_duration * i / total for i in range(total)]
    elapsed = 0.42 if args.elapsed is None else args.elapsed
    art = args.art
    if args.album_dir:
        tracks, cover = album_info(args.album_dir)
        total = len(tracks)
        track = max(1, min(track, total))
        lengths = [t['length'] for t in tracks]
        boundaries = [sum(lengths[:i]) for i in range(total)]
        album_duration = sum(lengths)
        current = tracks[track - 1]
        artist = current['artist'] or artist
        album = current['album'] or album
        date = current['date'] or date
        title = current['title']
        art = art or cover
        if args.elapsed is None:        # halfway through the chosen track
            elapsed = (boundaries[track - 1] + lengths[track - 1] / 2) / album_duration
    if art is None:
        art = _placeholder_art(os.path.join(os.path.dirname(os.path.abspath(args.out)),
                                            '_shot_art.png'))

    display = headless_display(width, height, settings_from_args(args), art, args.album_dir)

    status = {
        'playing': True,
        'artist': artist,
        'album': album,
        'track_title': title,
        'track_number': track,
        'total_tracks': total,
        'date': date,
        'progress': {
            'album_duration': album_duration,
            'elapsed': album_duration * elapsed,
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
