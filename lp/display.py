import io
import math
import os
import random
import threading
import time
import numpy as np
import pygame
import pygame.gfxdraw
from pygame._sdl2 import video as sdl2_video

from lpcore.vinyl.settings import VinylSettings
from lpcore.vinyl.fractals import NEBULA_VARIANTS
from lpcore.vinyl.render import VinylRenderer
from lpcore.vinyl.catalog import DARK_BG
from lpcore.vinyl.catalog import (
    DECOR_EMOJI, BLACK_GROOVE_COLORS, CLEAR_GROOVE_COLORS, INNER_GROOVE, JULIA_VARIANTS, LABEL_COLORS, LABEL_RADIUS, MANDELBROT_COLORS, MANDELBROT_GROOVE_COLORS, MANDELBROT_VARIANTS, MANDELBROT_ZOOMS, MUNAFO_GROOVE_COLORS, MUNAFO_VARIANTS, NEBULA_GROOVE_COLORS, OUTER_GROOVE, PICTURE_GROOVE_COLORS, PRERENDER_SIZE, RECORD_SUPERSAMPLE, STYLE_DISTRIBUTION, VINYL_BLACK, VINYL_COLORS, VINYL_GROOVE_COLORS, VINYL_LABEL, VINYL_LABEL_DARK)


PANEL_BG = (22, 22, 22)
TEXT_COLOR = (230, 230, 230)
DIM_TEXT = (80, 80, 80)
ACCENT = (200, 200, 200)

NEEDLE_COLOR = (200, 200, 200)


















# Vinyl cache locations now live in lpcore (re-exported here for api.py et al.).
from lpcore.vinyl.cache import (CACHE_DIR, NEBULA_CACHE_DIR, JULIA_CACHE_DIR,
                                MUNAFO_CACHE_DIR, MUNAFO_SOURCE_DIR)





# --- Nebula noise helpers ---









# --- Nebula palette functions ---
# Each takes (brightness, blend, t1, t2, t3, hue_shift) and returns (r, g, b)




























































class Display:
    def __init__(self, config, player, port=8000, settings=None):
        self.player = player
        self.settings = settings or VinylSettings()
        self.vinyl = VinylRenderer(self.settings)
        self.port = port
        self.config = config.get('display', {})
        self.fullscreen = self.config.get('fullscreen', False)
        self.width = self.config.get('width', 1280)
        self.height = self.config.get('height', 720)
        self.url = self.config.get('url', 'https://lp.example.com')

        self._dirty = True
        self._art_path = None
        self._art_texture = None
        self._status_cache = None
        self._record_angle = 0.0
        self._record_texture = None
        self._record_texture_key = None
        self._grooves_texture = None
        self._grooves_texture_key = None
        self._shine_texture = None
        self._shine_texture_key = None
        self._text_cache = {}
        self._needle_tex = None

        self.window = None
        self.renderer = None

        # Screenshot plumbing — request_screenshot() (called from API thread)
        # sets the event; the pygame loop captures the next frame and stores
        # PNG bytes for the requester to read.
        self._screenshot_event = threading.Event()
        self._screenshot_lock = threading.Lock()
        self._screenshot_data = None
        self._record_rect = None  # last-rendered record bounds, for screenshot blur

        player.on('play_start', self._mark_dirty)
        player.on('track_change', self._mark_dirty)
        player.on('album_end', self._mark_dirty)
        player.on('stop', self._mark_dirty)

    def _mark_dirty(self):
        self._dirty = True

    def request_screenshot(self, timeout=8.0):
        """Capture the current frame as PNG bytes. Thread-safe; intended to be
        called from the API thread. Returns bytes on success, None on timeout."""
        print(f'[share] request_screenshot called', flush=True)
        with self._screenshot_lock:
            self._screenshot_data = None
        self._dirty = True  # force a re-render so we capture the latest state
        self._screenshot_event.set()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._screenshot_lock:
                if self._screenshot_data is not None:
                    n = len(self._screenshot_data)
                    print(f'[share] request_screenshot got {n} bytes', flush=True)
                    return self._screenshot_data or None
            time.sleep(0.05)
        print(f'[share] request_screenshot TIMED OUT', flush=True)
        return None

    def _capture_screenshot_if_requested(self):
        """Called from the pygame loop, right after present()."""
        if not self._screenshot_event.is_set():
            return
        print(f'[share] _capture_screenshot_if_requested firing', flush=True)
        self._screenshot_event.clear()
        try:
            surf = self.renderer.to_surface()
            print(f'[share] to_surface size={surf.get_size()}', flush=True)
            # Normalize to the logical render resolution: when the window isn't
            # 16:9 the output is letterboxed, so crop to the centered render area
            # (matching SDL's logical-size scaling) before using logical-space
            # coords like _record_rect.
            ow, oh = surf.get_size()
            if (ow, oh) != (self.width, self.height):
                s = min(ow / self.width, oh / self.height)
                vw, vh = int(self.width * s), int(self.height * s)
                vx, vy = (ow - vw) // 2, (oh - vh) // 2
                surf = surf.subsurface(pygame.Rect(vx, vy, vw, vh)).copy()
                surf = pygame.transform.smoothscale(surf, (self.width, self.height))
                print(f'[share] de-letterboxed to {surf.get_size()}', flush=True)
            if self._record_rect is not None:
                rect = pygame.Rect(self._record_rect).clip(surf.get_rect())
                print(f'[share] record_rect={self._record_rect}, clipped={rect}', flush=True)
                if rect.width > 0 and rect.height > 0:
                    sub = surf.subsurface(rect).copy()
                    print(f'[share] subsurface ok, size={sub.get_size()}', flush=True)
                    if hasattr(pygame.transform, 'gaussian_blur'):
                        sub = pygame.transform.gaussian_blur(sub, 1)
                        print(f'[share] gaussian_blur ok', flush=True)
                    else:
                        sw, sh = sub.get_size()
                        small = pygame.transform.smoothscale(sub, (sw * 3 // 4, sh * 3 // 4))
                        sub = pygame.transform.smoothscale(small, (sw, sh))
                        print(f'[share] smoothscale-blur ok', flush=True)
                    surf.blit(sub, rect.topleft)
                    print(f'[share] blit back ok', flush=True)
            else:
                print(f'[share] no record_rect set', flush=True)
            # Downscale (or scale-to-fit) 1920×1080. PNG encoding stays small
            # enough and the saved image matches typical TV/display output.
            target_w, target_h = 1920, 1080
            if surf.get_size() != (target_w, target_h):
                surf = pygame.transform.smoothscale(surf, (target_w, target_h))
                print(f'[share] scaled to {target_w}x{target_h}', flush=True)
            buf = io.BytesIO()
            pygame.image.save(surf, buf, 'PNG')
            data = buf.getvalue()
            print(f'[share] PNG encoded: {len(data)} bytes', flush=True)
        except Exception as e:
            import traceback
            print(f'[share] EXCEPTION: {type(e).__name__}: {e}', flush=True)
            traceback.print_exc()
            data = b''
        with self._screenshot_lock:
            self._screenshot_data = data

    def run(self):
        # Tell SDL to use linear filtering when sampling textures. Without this,
        # SDL defaults to nearest-neighbor and the supersampled record texture
        # rotates with stair-stepped edges. Must be set before Renderer is created.
        os.environ.setdefault('SDL_HINT_RENDER_SCALE_QUALITY', '2')

        pygame.init()
        pygame.mixer.quit()  # Release audio device for VLC

        # self.width/height are the FIXED internal render resolution; all layout
        # math lives in that space. The window may be any size or fullscreen — the
        # renderer's logical size scales the render to fit, letterboxing to keep
        # aspect, so the look is identical at every window size.
        self.window = sdl2_video.Window('lp', size=(self.width, self.height))
        self.window.resizable = True
        if self.fullscreen:
            self.window.set_fullscreen(desktop=True)

        try:
            self.renderer = sdl2_video.Renderer(self.window, accelerated=1, vsync=True)
            print(f'display: GPU renderer, render res {self.width}x{self.height} (SS={RECORD_SUPERSAMPLE})', flush=True)
        except pygame.error as e:
            print(f'WARN: GPU renderer unavailable ({e}); falling back to software', flush=True)
            self.renderer = sdl2_video.Renderer(self.window, accelerated=0)

        self.renderer.logical_size = (self.width, self.height)

        # Window events that change the output size (or expose a stale frame) —
        # re-assert logical size and force a redraw, since we only present on dirty.
        resize_events = {getattr(pygame, n) for n in
                         ('WINDOWRESIZED', 'WINDOWSIZECHANGED', 'WINDOWEXPOSED',
                          'WINDOWMAXIMIZED', 'WINDOWRESTORED', 'VIDEORESIZE')
                         if hasattr(pygame, n)}

        self.clock = pygame.time.Clock()

        self._load_fonts()
        self._build_needle_texture()
        self._poll_counter = 0

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        running = False
                    elif event.key == pygame.K_ESCAPE:
                        # Esc leaves fullscreen if in it, otherwise quits.
                        if self.fullscreen:
                            self._toggle_fullscreen()
                        else:
                            running = False
                    elif event.key in (pygame.K_f, pygame.K_F11):
                        self._toggle_fullscreen()
                elif event.type in resize_events:
                    self.renderer.logical_size = (self.width, self.height)
                    self._dirty = True

            self._poll_counter += 1
            if self._poll_counter >= 15:
                self._poll_counter = 0
                new_status = self.player.get_status()
                if new_status != self._status_cache:
                    self._status_cache = new_status
                    self._dirty = True

            playing = self._status_cache and self._status_cache.get('playing')

            if playing:
                self._record_angle = (self._record_angle + 0.8) % 360
                self._dirty = True

            if self._dirty:
                self._dirty = False
                self._render()
                self.renderer.present()
                self._capture_screenshot_if_requested()

            self.clock.tick(30)

        pygame.quit()

    def _toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.window.set_fullscreen(desktop=True)
        else:
            self.window.set_windowed()
        # New output size → recompute the letterbox scale, then redraw.
        self.renderer.logical_size = (self.width, self.height)
        self._dirty = True

    def _load_fonts(self):
        self._font_large = pygame.font.SysFont('sans', int(self.height * 0.03))
        self._font_medium = pygame.font.SysFont('sans', int(self.height * 0.026))
        self._font_small = pygame.font.SysFont('sans', int(self.height * 0.02))
        self._font_idle = pygame.font.SysFont('sans', int(self.height * 0.12))

    def _text_tex(self, key, font, text, color):
        """Get a cached text Texture; re-render only when content/color changes."""
        cached = self._text_cache.get(key)
        if cached and cached[0] == text and cached[1] == color:
            return cached[2], cached[3]
        surf = font.render(text, True, color)
        tex = sdl2_video.Texture.from_surface(self.renderer, surf)
        rect = surf.get_rect()
        self._text_cache[key] = (text, color, tex, rect)
        return tex, rect

    def _build_needle_texture(self):
        """Pre-build the small needle-tip circle as a Texture (drawn each frame)."""
        s = pygame.Surface((9, 9), pygame.SRCALPHA)
        pygame.draw.circle(s, NEEDLE_COLOR, (4, 4), 3)
        self._needle_tex = sdl2_video.Texture.from_surface(self.renderer, s)




























    def _render(self):
        status = self._status_cache or self.player.get_status()

        if not status.get('playing'):
            self._render_idle()
        else:
            self._render_playing(status)

    def _render_idle(self):
        self._record_rect = None
        self.renderer.draw_color = DARK_BG
        self.renderer.clear()

        tex, rect = self._text_tex('idle_lp', self._font_idle, 'lp', DIM_TEXT)
        dst = rect.copy()
        dst.center = (self.width // 2, self.height // 2 - int(self.height * 0.05))
        tex.draw(dstrect=dst)

        tex, rect = self._text_tex('idle_url', self._font_small, self.url, DIM_TEXT)
        dst = rect.copy()
        dst.center = (self.width // 2, self.height // 2 + int(self.height * 0.08))
        tex.draw(dstrect=dst)

    def _render_playing(self, status):
        self.renderer.draw_color = DARK_BG
        self.renderer.clear()

        art_width = int(self.height * 1.0)
        if art_width > int(self.width * 0.56):
            art_width = int(self.width * 0.56)
        meta_x = art_width
        meta_width = self.width - art_width

        # Album art — upload to a Texture once per art change
        art_path, _ = self.player.get_current_song_info()
        if art_path != self._art_path:
            self._art_path = art_path
            self._art_texture = None
            if art_path:
                try:
                    img = pygame.image.load(art_path)
                    art_surf = pygame.transform.smoothscale(img, (art_width, self.height))
                    self._art_texture = sdl2_video.Texture.from_surface(self.renderer, art_surf)
                except Exception:
                    self._art_texture = None

        if self._art_texture:
            self._art_texture.draw(dstrect=pygame.Rect(0, 0, art_width, self.height))
        else:
            self.renderer.draw_color = PANEL_BG
            self.renderer.fill_rect(pygame.Rect(0, 0, art_width, self.height))

        # Metadata panel
        self.renderer.draw_color = PANEL_BG
        self.renderer.fill_rect(pygame.Rect(meta_x, 0, meta_width, self.height))

        pad = int(meta_width * 0.08)
        x = meta_x + pad
        y = int(self.height * 0.08)

        # Artist
        if status.get('artist'):
            tex, rect = self._text_tex('artist', self._font_large, status['artist'], TEXT_COLOR)
            tex.draw(dstrect=pygame.Rect(x, y, rect.w, rect.h))
            y += rect.h + int(self.height * 0.015)

        # Album
        if status.get('album'):
            tex, rect = self._text_tex('album', self._font_large, status['album'], ACCENT)
            tex.draw(dstrect=pygame.Rect(x, y, rect.w, rect.h))
            y += rect.h + int(self.height * 0.012)

        # Year
        date = status.get('date') or ''
        year = date[:4] if len(date) >= 4 else date
        if year:
            tex, rect = self._text_tex('year', self._font_medium, year, DIM_TEXT)
            tex.draw(dstrect=pygame.Rect(x, y, rect.w, rect.h))
            y += rect.h + int(self.height * 0.02)

        # Spinning record — size to fit remaining space
        progress = status.get('progress', {})
        album_dur = progress.get('album_duration', 0)
        elapsed = progress.get('elapsed', 0)
        boundaries = progress.get('track_boundaries', [])

        remaining_h = self.height - y - int(self.height * 0.06)
        max_by_width = (meta_width - pad * 2) // 2
        record_size = min(remaining_h // 2, max_by_width)
        record_size = max(record_size, 40)

        # Get album path for vinyl style
        album_path = None
        with self.player._lock:
            album_path = self.player.album_path

        # Body: supersampled texture, GPU downscales 2:1 during draw.
        body_key = (album_path, self.settings.style, self.settings.label,
                    self.settings.brightness, record_size, 'body',
                    self.settings.label_text, self.settings.label_font,
                    self.settings.artist_color, self.settings.album_color,
                    self.settings.decor1, self.settings.decor1_color,
                    self.settings.decor2, self.settings.decor2_color,
                    status.get('artist'), status.get('album'))
        if body_key != self._record_texture_key:
            self._record_texture_key = body_key
            record_surf = self.vinyl.build_record(record_size * RECORD_SUPERSAMPLE,
                                             boundaries, album_dur, art_path, album_path,
                                             status.get('artist'), status.get('album'))
            self._record_texture = sdl2_video.Texture.from_surface(self.renderer, record_surf)

        # Grooves overlay: display-resolution texture, no GPU downscale,
        # rotated with the body. Avoids moiré from sampling dense rings.
        style = self.vinyl.get_vinyl_style(album_path) or {'type': 'black'}
        grooves_key = (style.get('type'), style.get('color'), style.get('variant'),
                       self.settings.brightness, record_size, tuple(boundaries))
        if grooves_key != self._grooves_texture_key:
            self._grooves_texture_key = grooves_key
            grooves_surf, blend_mode = self.vinyl.build_grooves_overlay(record_size, style, boundaries, album_dur)
            self._grooves_texture = sdl2_video.Texture.from_surface(self.renderer, grooves_surf)
            self._grooves_texture.blend_mode = (
                pygame.BLENDMODE_ADD if blend_mode == 'add' else pygame.BLENDMODE_BLEND)

        # Specular shine: built per (style type, brightness, size) — independent
        # of rotation and album, since it's the fixed room-light reflection.
        shine_key = (style.get('type'), self.settings.brightness, record_size)
        if shine_key != self._shine_texture_key:
            self._shine_texture_key = shine_key
            shine_surf = self.vinyl.build_shine_overlay(record_size, style)
            self._shine_texture = sdl2_video.Texture.from_surface(self.renderer, shine_surf)
            self._shine_texture.blend_mode = pygame.BLENDMODE_BLEND

        rec_cx = meta_x + meta_width // 2
        rec_cy = y + record_size + int(self.height * 0.01)
        d = record_size * 2
        rec_dst = pygame.Rect(rec_cx - record_size, rec_cy - record_size, d, d)
        self._record_rect = rec_dst
        self._record_texture.draw(dstrect=rec_dst, angle=self._record_angle)
        self._grooves_texture.draw(dstrect=rec_dst, angle=self._record_angle)
        # Drawn WITHOUT angle — the reflection stays fixed as the disc spins.
        self._shine_texture.draw(dstrect=rec_dst)

        # Needle — drawn on top, not rotating with the record
        if album_dur > 0:
            frac = min(elapsed / album_dur, 1.0)
        else:
            frac = 0.0
        groove_range = (OUTER_GROOVE - INNER_GROOVE) * record_size
        needle_r = record_size * OUTER_GROOVE - frac * groove_range
        needle_angle = math.radians(-60)
        needle_x = int(rec_cx + needle_r * math.cos(needle_angle))
        needle_y = int(rec_cy + needle_r * math.sin(needle_angle))

        # Tonearm — two parallel lines to simulate the old width=2
        pivot_x = int(rec_cx + record_size * 1.15)
        pivot_y = int(rec_cy - record_size * 0.9)
        self.renderer.draw_color = (70, 70, 70)
        self.renderer.draw_line((pivot_x, pivot_y), (needle_x, needle_y))
        self.renderer.draw_line((pivot_x, pivot_y + 1), (needle_x, needle_y + 1))

        # Needle dot — pre-built tiny texture
        self._needle_tex.draw(dstrect=pygame.Rect(needle_x - 4, needle_y - 4, 9, 9))
