#!/usr/bin/env python
"""Dev-only vinyl inspector.

A spinning record + tonearm on a black background, with NO playback and NO
VLC. Reuses the real rendering path — lpcore.vinyl.VinylRenderer (build_record,
build_grooves_overlay, build_shine_overlay) + lp.display needle geometry — so
what you see matches the app.

Cycle through every vinyl style to inspect each render, OR drive it live from
the real web UI: this also serves the lp web UI on http://localhost:8000 bound
to the same player, so picking a style / label / brightness there updates the
spinning record instantly.

Controls
  → / Space   next style
  ←           previous style
  ↑ / ↓       brightness +/- 10
  [ / ]       record bigger / smaller
  r           re-randomize the album seed (changes random/pattern picks)
  s           save a PNG of the current frame to dev_out/
  Esc / q     quit

Optional: pass a cover image path to test picture-disc / album-art labels:
  python dev_spin.py /path/to/cover.jpg
"""
import math
import os
import random
import sys
import threading
import time

import pygame
import uvicorn
import yaml
from pygame._sdl2 import video as sdl2_video

from lp.display import (Display, OUTER_GROOVE, INNER_GROOVE, RECORD_SUPERSAMPLE,
                        VINYL_COLORS, MANDELBROT_VARIANTS, NEBULA_VARIANTS,
                        MUNAFO_VARIANTS)
from lp.api import create_app
from lpcore.library import Library
from lpcore.vinyl.settings import VinylSettings

WIN_W, WIN_H = 1000, 800
WEB_PORT = 8000


def build_style_list():
    styles = ['black', 'clear', 'picture']
    styles += ['color-' + c for c in VINYL_COLORS]
    styles += ['mandelbrot-%s-%s' % (v[4], v[5]) for v in MANDELBROT_VARIANTS]
    styles += ['nebula-' + v[2] for v in NEBULA_VARIANTS]
    styles += ['munafo-' + v[0] for v in MUNAFO_VARIANTS]
    styles += ['pattern-mandelbrot', 'pattern-nebula', 'pattern-munafo']
    return styles


class MockPlayer:
    """Just enough surface for the Display render helpers — no VLC, no audio.

    Vinyl display config lives in a VinylSettings (driven by arrow keys / the
    web UI), not on the player.
    """
    def __init__(self):
        self.album_path = '/dev/inspect'
        self._lock = threading.Lock()

    def on(self, event, cb):
        pass  # Display subscribes to player events; we never fire them.


def start_web_ui(player, settings):
    """Serve the real lp web UI on WEB_PORT, bound to our mock player + settings.

    POST /api/settings/vinyl (and label/brightness) mutate the shared
    VinylSettings the render loop reads each frame — so the web UI controls the
    spinning record directly. No display/scrobbler/state needed for that.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(here, 'static')
    music_path = '/nonexistent'
    try:
        with open(os.path.join(here, 'config.yml')) as f:
            music_path = yaml.safe_load(f).get('music_library_path', music_path)
    except Exception:
        pass
    library = Library(music_path)  # empty/0 albums is fine; we only need settings
    from lp.state import UserState
    state = UserState(os.path.join(here, '.lp_state.json'))
    app = create_app(player, library, static_dir, state=state, settings=settings)
    t = threading.Thread(
        target=uvicorn.run, args=(app,),
        kwargs={'host': '0.0.0.0', 'port': WEB_PORT, 'log_level': 'warning'},
        daemon=True,
    )
    t.start()
    print(f'web UI: http://localhost:{WEB_PORT}  (pick a style there to update the record)')


def main():
    art_path = sys.argv[1] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) else None

    styles = build_style_list()
    idx = 0
    seed = 0  # appended to album_path to re-randomize random/pattern picks

    config = {'display': {'width': WIN_W, 'height': WIN_H, 'fullscreen': False}}
    player = MockPlayer()
    settings = VinylSettings(style=styles[idx])
    disp = Display(config, player, settings=settings)
    start_web_ui(player, settings)

    # --- Renderer setup (mirrors Display.run() without the player loop) ---
    os.environ.setdefault('SDL_HINT_RENDER_SCALE_QUALITY', '2')
    pygame.init()
    try:
        pygame.mixer.quit()
    except Exception:
        pass
    window = sdl2_video.Window('lp dev — vinyl inspector', size=(WIN_W, WIN_H))
    renderer = sdl2_video.Renderer(window, accelerated=1, vsync=True)
    disp.window = window
    disp.renderer = renderer
    disp.width, disp.height = WIN_W, WIN_H
    disp._load_fonts()
    disp._build_needle_texture()
    clock = pygame.time.Clock()

    # Synthetic album with realistic, uneven track lengths so the music-zone
    # gaps aren't evenly spaced. Regenerated on reseed ('r').
    def make_tracks(s):
        rng = random.Random(s)
        lengths = [rng.uniform(110.0, 360.0) for _ in range(rng.randint(6, 12))]
        bounds, c = [], 0.0
        for L in lengths:
            bounds.append(c)
            c += L
        return bounds, c

    boundaries, album_dur = make_tracks(seed)
    tracks_seed = seed

    record_size = 300
    angle = 0.0
    body_tex = body_key = None
    grooves_tex = grooves_key = None
    shine_tex = shine_key = None

    def album_path():
        return f'/dev/inspect/{seed}'

    print('lp vinyl inspector — see header comment for controls.')
    print(f'{len(styles)} styles. Cover: {art_path or "(none — pass a path to test album art)"}')

    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif e.key in (pygame.K_RIGHT, pygame.K_SPACE):
                    idx = (idx + 1) % len(styles)
                    settings.style = styles[idx]
                elif e.key == pygame.K_LEFT:
                    idx = (idx - 1) % len(styles)
                    settings.style = styles[idx]
                elif e.key == pygame.K_UP:
                    settings.brightness = min(100, settings.brightness + 10)
                elif e.key == pygame.K_DOWN:
                    settings.brightness = max(0, settings.brightness - 10)
                elif e.key == pygame.K_RIGHTBRACKET:
                    record_size = min(380, record_size + 20)
                elif e.key == pygame.K_LEFTBRACKET:
                    record_size = max(120, record_size - 20)
                elif e.key == pygame.K_r:
                    seed += 1
                elif e.key == pygame.K_s:
                    os.makedirs('dev_out', exist_ok=True)
                    fn = f'dev_out/{settings.style.replace("/", "_")}.png'
                    pygame.image.save(renderer.to_surface(), fn)
                    print(f'saved {fn}')

        # Render whatever the player currently holds — set by our arrow keys
        # OR live from the web UI (POST /api/settings/vinyl etc).
        if seed != tracks_seed:
            tracks_seed = seed
            boundaries, album_dur = make_tracks(seed)

        cur_style = settings.style
        ap = album_path()
        style = disp.vinyl.get_vinyl_style(ap) or {'type': 'black'}

        # Rebuild textures only when the inputs change. Sample metadata so the
        # label text renders in the inspector.
        SAMPLE_ARTIST, SAMPLE_ALBUM = 'KARMANDAKAH', 'DIAMOND MORNING'
        bkey = (cur_style, settings.label, record_size,
                settings.brightness, seed,
                settings.label_text, settings.label_font,
                settings.artist_color, settings.album_color,
                settings.decor1, settings.decor1_color,
                settings.decor2, settings.decor2_color)
        if bkey != body_key:
            body_key = bkey
            try:
                surf = disp.vinyl.build_record(record_size * RECORD_SUPERSAMPLE,
                                          boundaries, album_dur, art_path, ap,
                                          SAMPLE_ARTIST, SAMPLE_ALBUM)
                body_tex = sdl2_video.Texture.from_surface(renderer, surf)
            except Exception as ex:
                print(f'body build failed for {cur_style}: {ex}')
                body_tex = None
            try:
                gsurf, blend = disp.vinyl.build_grooves_overlay(record_size, style,
                                                           boundaries, album_dur)
                grooves_tex = sdl2_video.Texture.from_surface(renderer, gsurf)
                grooves_tex.blend_mode = (pygame.BLENDMODE_ADD
                                          if blend == 'add' else pygame.BLENDMODE_BLEND)
            except Exception as ex:
                print(f'grooves build failed for {cur_style}: {ex}')
                grooves_tex = None

        # Fixed specular shine (depends only on style type / brightness / size).
        skey = (style.get('type'), settings.brightness, record_size)
        if skey != shine_key:
            shine_key = skey
            try:
                ssurf = disp.vinyl.build_shine_overlay(record_size, style)
                shine_tex = sdl2_video.Texture.from_surface(renderer, ssurf)
                shine_tex.blend_mode = pygame.BLENDMODE_BLEND
            except Exception as ex:
                print(f'shine build failed for {cur_style}: {ex}')
                shine_tex = None

        angle = (angle + 0.8) % 360
        # Needle sweeps the playable band on a 24s loop.
        frac = (time.monotonic() % 24.0) / 24.0

        renderer.draw_color = (0, 0, 0)
        renderer.clear()

        cx, cy = WIN_W // 2, WIN_H // 2 + 20
        d = record_size * 2
        rect = pygame.Rect(cx - record_size, cy - record_size, d, d)
        if body_tex:
            body_tex.draw(dstrect=rect, angle=angle)
        if grooves_tex:
            grooves_tex.draw(dstrect=rect, angle=angle)
        if shine_tex:
            shine_tex.draw(dstrect=rect)  # no angle — fixed reflection

        # Tonearm + needle (same geometry as Display._render_playing)
        groove_range = (OUTER_GROOVE - INNER_GROOVE) * record_size
        needle_r = record_size * OUTER_GROOVE - frac * groove_range
        na = math.radians(-60)
        nx = int(cx + needle_r * math.cos(na))
        ny = int(cy + needle_r * math.sin(na))
        px = int(cx + record_size * 1.15)
        py = int(cy - record_size * 0.9)
        renderer.draw_color = (70, 70, 70)
        renderer.draw_line((px, py), (nx, ny))
        renderer.draw_line((px, py + 1), (nx, ny + 1))
        disp._needle_tex.draw(dstrect=pygame.Rect(nx - 4, ny - 4, 9, 9))

        # HUD: live style id (+ list position when it's one of ours) + brightness
        pos = f'{styles.index(cur_style) + 1}/{len(styles)}' if cur_style in styles else 'web'
        hud = f'[{pos}]  {cur_style}   label={settings.label}  bright={settings.brightness}%'
        tex, r = disp._text_tex('hud', disp._font_small, hud, (210, 210, 210))
        tex.draw(dstrect=pygame.Rect(20, 16, r.w, r.h))

        renderer.present()
        clock.tick(30)

    pygame.quit()


if __name__ == '__main__':
    main()
