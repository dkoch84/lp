"""VinylRenderer — builds the spinning-vinyl surfaces (body, grooves, shine,
labels) from a VinylSettings + album context. Pure pygame/numpy; no SDL window,
no audio. lp's Display and lp-deck both drive it.
"""
import math
import os
import random

import numpy as np
import pygame
import pygame.gfxdraw

from lpcore.vinyl.settings import VinylSettings
from lpcore.vinyl.catalog import (
    CLEAR_GROOVE_COLORS, DARK_BG, DECOR_EMOJI, INNER_GROOVE, LABEL_COLORS, LABEL_RADIUS, MUNAFO_GROOVE_COLORS, OUTER_GROOVE, RECORD_SUPERSAMPLE, VINYL_BLACK, VINYL_COLORS, VINYL_GROOVE_COLORS, VINYL_LABEL, VINYL_LABEL_DARK)
from lpcore.vinyl.cache import CACHE_DIR, JULIA_CACHE_DIR, MUNAFO_CACHE_DIR, NEBULA_CACHE_DIR
from lpcore.vinyl.fractals import (
    _pick_vinyl_style, _render_mandelbrot_surface, _render_munafo_surface, _render_nebula_surface)


def _resolve_color(val, fallback):
    """'auto'/None → fallback accent; '#rrggbb' → rgb tuple."""
    if isinstance(val, str) and val.startswith('#') and len(val) == 7:
        try:
            return (int(val[1:3], 16), int(val[3:5], 16), int(val[5:7], 16))
        except ValueError:
            pass
    return tuple(fallback[:3])


class VinylRenderer:
    """Stateful renderer: holds the display settings + per-album render caches."""

    def __init__(self, settings=None):
        self.settings = settings or VinylSettings()
        self._label_art = None
        self._label_art_path = None
        self._current_vinyl_style = None
        self._current_album_path = None
        self._current_override = None
        self._pattern_label_cache = None
        self._julia_label_cache = None

    def _get_circular_art(self, art_path, radius):
        """Get album art masked into a circle at the given radius."""
        try:
            img = pygame.image.load(art_path)
            d = radius * 2
            # Force RGBA so BLEND_RGBA_MULT actually masks alpha (JPEG loads as RGB).
            rgba = pygame.Surface((d, d), pygame.SRCALPHA)
            scaled = pygame.transform.smoothscale(img, (d, d))
            rgba.blit(scaled, (0, 0))
            circle_mask = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(circle_mask, (255, 255, 255, 255), (radius, radius), radius)
            rgba.blit(circle_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            return rgba
        except Exception:
            return None

    def _get_label_art(self, art_path, label_r):
        """Get circular album art for the record label, cached by path."""
        if art_path == self._label_art_path and self._label_art is not None:
            if self._label_art.get_width() == label_r * 2:
                return self._label_art
        self._label_art_path = art_path
        self._label_art = self._get_circular_art(art_path, label_r)
        return self._label_art

    def _get_julia_label(self, name, label_r):
        """Load a pre-rendered Julia disc and scale to the label radius.
        Cached on the Display instance by (name, label_r)."""
        key = (name, label_r)
        cached = getattr(self, '_julia_label_cache', {})
        if key in cached:
            return cached[key]
        path = os.path.join(JULIA_CACHE_DIR, f'{name}.png')
        if not os.path.isfile(path):
            return None
        try:
            img = pygame.image.load(path)
        except Exception:
            return None
        d = label_r * 2
        scaled = pygame.transform.smoothscale(img, (d, d))
        # Ensure RGBA so alpha is preserved on later blits.
        target = pygame.Surface((d, d), pygame.SRCALPHA)
        target.blit(scaled, (0, 0))
        cached[key] = target
        self._julia_label_cache = cached
        return target

    def _get_pattern_label(self, label_setting, label_r):
        """Render a fractal cache (mandelbrot / nebula / munafo) as a label.
        `label_setting` is like 'mandelbrot-seahorse-purple', 'nebula-galaxy',
        or 'munafo-deep5_v1'. Returns a circular RGBA surface or None."""
        key = (label_setting, label_r)
        cached = getattr(self, '_pattern_label_cache', {})
        if key in cached:
            return cached[key]

        if label_setting.startswith('mandelbrot-'):
            path = os.path.join(CACHE_DIR, f'{label_setting[len("mandelbrot-"):]}.png')
        elif label_setting.startswith('nebula-'):
            path = os.path.join(NEBULA_CACHE_DIR, f'{label_setting[len("nebula-"):]}.png')
        elif label_setting.startswith('munafo-'):
            path = os.path.join(MUNAFO_CACHE_DIR, f'{label_setting[len("munafo-"):]}.png')
        else:
            return None

        if not os.path.isfile(path):
            return None
        try:
            img = pygame.image.load(path)
        except Exception:
            return None
        d = label_r * 2
        scaled = pygame.transform.smoothscale(img, (d, d))
        # Re-mask to the label radius — source PNGs are masked to the full
        # vinyl disc, which is larger than the label.
        target = pygame.Surface((d, d), pygame.SRCALPHA)
        target.blit(scaled, (0, 0))
        mask = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (label_r, label_r), label_r)
        target.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        cached[key] = target
        self._pattern_label_cache = cached
        return target

    @staticmethod
    def _draw_fake_label_text(surf, cx, cy, label_r, accent_c):
        """Draw chickenscratch fake text on a colored record label."""
        rng = random.Random(42)
        d = label_r * 2
        tmp = pygame.Surface((d, d), pygame.SRCALPHA)
        lx, ly = label_r, label_r

        text_col = (*accent_c[:3], 140)
        bold_col = (*accent_c[:3], 180)
        ring_col = (*accent_c[:3], 50)

        # Decorative rings like a real label
        pygame.draw.circle(tmp, ring_col, (lx, ly), int(label_r * 0.88), 1)
        pygame.draw.circle(tmp, ring_col, (lx, ly), int(label_r * 0.55), 1)

        # "Title" line — slightly thicker dashes
        ty = ly - int(label_r * 0.28)
        hw = int(label_r * 0.45)
        x = lx - hw
        while x < lx + hw:
            w = rng.randint(max(2, label_r // 10), max(4, label_r // 4))
            ex = min(x + w, lx + hw)
            pygame.draw.line(tmp, bold_col, (x, ty), (ex, ty), 2)
            x = ex + rng.randint(2, max(3, label_r // 12))

        # Smaller text lines
        for yo in [-0.08, 0.08, 0.22, 0.38]:
            y = ly + int(yo * label_r)
            da = abs(yo) + 0.15
            lhw = int(math.sqrt(max(0, 1 - da * da)) * label_r * 0.45)
            x = lx - lhw
            while x < lx + lhw:
                w = rng.randint(max(2, label_r // 15), max(3, label_r // 6))
                ex = min(x + w, lx + lhw)
                pygame.draw.line(tmp, text_col, (x, y), (ex, y), 1)
                x = ex + rng.randint(1, max(2, label_r // 10))

        surf.blit(tmp, (cx - label_r, cy - label_r))

    @staticmethod
    def _draw_label_decor(surf, cx, cy, label_r, slots, seed=0, vertical=False):
        """Place monochrome critter silhouettes in the label's empty spaces — one
        per slot. `vertical` puts them top/bottom (for centered straight/blocky
        text); otherwise left/right (for curved top/bottom text). `slots` is up
        to two (name, rgb) pairs; name may be a critter, 'random', or 'none'."""
        path = pygame.font.match_font('notoemoji')   # monochrome outline glyphs
        if not path:
            return
        font = pygame.font.Font(path, 96)
        target = max(8, int(label_r * 0.42))
        if vertical:
            off = int(label_r * 0.62)
            positions = [(cx, cy - off), (cx, cy + off)]   # 12 and 6 o'clock
        else:
            off = int(label_r * 0.5)
            positions = [(cx - off, cy), (cx + off, cy)]   # 9 and 3 o'clock
        rng = random.Random(seed)
        for (name, col), (sx, sy) in zip(slots, positions):
            if not name or name == 'none':
                continue
            if name == 'random':
                name = rng.choice(list(DECOR_EMOJI))
            if name not in DECOR_EMOJI:
                continue
            try:
                g = font.render(DECOR_EMOJI[name], True, tuple(col[:3]))
            except Exception:
                continue
            g = pygame.transform.smoothscale(g, (target, target))
            surf.blit(g, g.get_rect(center=(sx, sy)))

    @staticmethod
    def _draw_arc_text(surf, cx, cy, radius, text, font, color, top=True):
        """Blit `text` curved along a circle arc, centered at top or bottom."""
        if not text:
            return
        glyphs = [(ch, font.render(ch, True, color)) for ch in text]
        widths = [g.get_width() for _, g in glyphs]
        gap = max(1, int(font.get_height() * 0.06))
        total_w = sum(widths) + gap * (len(text) - 1)
        total_ang = total_w / float(radius)
        if top:
            a = -math.pi / 2 - total_ang / 2.0   # start left of top center
            step = 1.0
        else:
            a = math.pi / 2 + total_ang / 2.0     # start left of bottom center
            step = -1.0
        for (ch, g), w in zip(glyphs, widths):
            char_ang = w / float(radius)
            ca = a + step * char_ang / 2.0
            px = cx + radius * math.cos(ca)
            py = cy + radius * math.sin(ca)
            deg = -(math.degrees(ca) + 90) if top else -(math.degrees(ca) - 90)
            rot = pygame.transform.rotate(g, deg)
            surf.blit(rot, rot.get_rect(center=(int(px), int(py))))
            a += step * (char_ang + gap / float(radius))

    @staticmethod
    def _draw_label_text(surf, cx, cy, label_r, accent_c, artist=None, album=None,
                         mode='curved', font_name='serif',
                         artist_color=None, album_color=None):
        """Real artist/album text on a colored label.

        mode: 'none'     — no text at all (blank label)
              'curved'   — artist on the top arc, album on the bottom arc
              'straight'  — centered horizontal lines
              'blocky'    — centered, heavy/condensed block lettering
        Falls back to abstract chickenscratch when there's no metadata.
        """
        if mode == 'none':
            return
        if not artist and not album:
            VinylRenderer._draw_fake_label_text(surf, cx, cy, label_r, accent_c)
            return
        d = label_r * 2
        tmp = pygame.Surface((d, d), pygame.SRCALPHA)
        lx, ly = label_r, label_r
        ring_col = (*accent_c[:3], 60)
        a_col = (*(artist_color or accent_c[:3]), 235)
        b_col = (*(album_color or accent_c[:3]), 235)
        pygame.font.init()

        if mode == 'curved':
            pygame.draw.circle(tmp, ring_col, (lx, ly), int(label_r * 0.92), 1)
            font = pygame.font.SysFont(font_name, max(8, int(label_r * 0.15)), bold=True)
            text_r = int(label_r * 0.74)
            if artist:
                VinylRenderer._draw_arc_text(tmp, lx, ly, text_r, artist.upper(), font, a_col, top=True)
            if album:
                VinylRenderer._draw_arc_text(tmp, lx, ly, text_r, album.upper(), font, b_col, top=False)
        else:
            blocky = mode == 'blocky'
            fs = int(label_r * (0.22 if blocky else 0.17))
            font = pygame.font.SysFont(font_name, max(8, fs), bold=True)
            lines = [(t.upper(), c) for t, c in ((artist, a_col), (album, b_col)) if t]
            rendered = []
            maxw = int(label_r * 1.45)
            for ln, c in lines:
                g = font.render(ln, True, c)
                if g.get_width() > maxw:   # shrink long names proportionally (no squish)
                    sc = maxw / g.get_width()
                    g = pygame.transform.smoothscale(
                        g, (maxw, max(1, int(g.get_height() * sc))))
                rendered.append(g)
            gap = int(label_r * (0.20 if blocky else 0.16))   # roomy artist↔album gap
            total_h = sum(g.get_height() for g in rendered) + gap * (len(rendered) - 1)
            y = ly - total_h // 2
            for g in rendered:
                tmp.blit(g, g.get_rect(midtop=(lx, y)))
                y += g.get_height() + gap

        surf.blit(tmp, (cx - label_r, cy - label_r))

    def get_vinyl_style(self, album_path):
        """Get or compute vinyl style for current album."""
        override = self.settings.style
        cache_key = (album_path, override)
        if cache_key != (self._current_album_path, getattr(self, '_current_override', None)):
            self._current_album_path = album_path
            self._current_override = override
            self._current_vinyl_style = _pick_vinyl_style(album_path, override) if album_path else None
        return self._current_vinyl_style

    def build_record(self, size, boundaries, album_dur, art_path=None, album_path=None,
                      artist=None, album=None):
        """Build the vinyl record body (no grooves/track marks — those go on the overlay)."""
        d = size * 2
        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        center = (size, size)

        style = self.get_vinyl_style(album_path)
        if not style:
            style = {'type': 'black'}

        style_type = style['type']

        if style_type == 'picture' and art_path:
            pic = self._get_circular_art(art_path, size)
            if pic:
                surf.blit(pic, (0, 0))
            else:
                self._draw_black_vinyl(surf, size, center)
        elif style_type == 'clear':
            self._draw_clear_vinyl(surf, size, center)
        elif style_type == 'color':
            base = VINYL_COLORS.get(style.get('color'), VINYL_BLACK[0])
            self._draw_color_vinyl(surf, size, center, base)
        elif style_type == 'mandelbrot':
            variant = style['variant']
            self._draw_mandelbrot_vinyl(surf, size, center, variant)
        elif style_type == 'nebula':
            variant = style['variant']
            self._draw_nebula_vinyl(surf, size, center, variant)
        elif style_type == 'munafo':
            variant = style['variant']
            self._draw_munafo_vinyl(surf, size, center, variant)
        elif style_type == 'pattern':
            # Pattern picture-disc: fractal as the full disc body, no label.
            sub = style.get('sub') or {}
            sub_type = sub.get('type')
            if sub_type == 'mandelbrot':
                self._draw_mandelbrot_vinyl(surf, size, center, sub['variant'])
            elif sub_type == 'nebula':
                self._draw_nebula_vinyl(surf, size, center, sub['variant'])
            elif sub_type == 'munafo':
                self._draw_munafo_vinyl(surf, size, center, sub['variant'])
            else:
                self._draw_black_vinyl(surf, size, center)
        else:
            self._draw_black_vinyl(surf, size, center)

        # Label — album art, colored, fractal, or fallback. Skip entirely
        # for picture-disc styles ('picture' = album art disc, 'pattern' =
        # fractal disc) since those use the body all the way through.
        if style_type not in ('picture', 'pattern'):
            label_r = int(size * LABEL_RADIUS)
            label_setting = self.settings.label
            text_mode = self.settings.label_text
            text_font = self.settings.label_font

            # Text + decorations render over EVERY label type except the
            # full-disc picture/pattern styles (handled by the outer guard).
            # Solid labels get an accent derived from their color; image labels
            # (album art / fractal / julia) get a light default for 'auto'.
            IMG_ACCENT = (245, 245, 245)
            is_image = False

            if label_setting == 'art':
                label_art = self._get_label_art(art_path, label_r) if art_path else None
                if label_art:
                    surf.blit(label_art, (size - label_r, size - label_r))
                    label_accent, is_image = IMG_ACCENT, True
                else:
                    pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                    label_accent = VINYL_LABEL_DARK
            elif label_setting.startswith('color-'):
                # Any vinyl color doubles as a label color (unified palette).
                color_name = label_setting[len('color-'):]
                main_c = VINYL_COLORS.get(color_name, VINYL_LABEL)
                label_accent = tuple(int(c * 0.55) for c in main_c)
                pygame.draw.circle(surf, main_c, center, label_r)
            elif label_setting.startswith('label-'):
                # Legacy label-color palette (superseded by color-*).
                color_name = label_setting[len('label-'):]
                main_c, label_accent = LABEL_COLORS.get(color_name, (VINYL_LABEL, VINYL_LABEL_DARK))
                pygame.draw.circle(surf, main_c, center, label_r)
            elif label_setting.startswith('julia-'):
                jl = self._get_julia_label(label_setting[len('julia-'):], label_r)
                if jl:
                    surf.blit(jl, (size - label_r, size - label_r))
                    label_accent, is_image = IMG_ACCENT, True
                else:
                    pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                    label_accent = VINYL_LABEL_DARK
            elif (label_setting.startswith('mandelbrot-')
                  or label_setting.startswith('nebula-')
                  or label_setting.startswith('munafo-')):
                fl = self._get_pattern_label(label_setting, label_r)
                if fl:
                    surf.blit(fl, (size - label_r, size - label_r))
                    label_accent, is_image = IMG_ACCENT, True
                else:
                    pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                    label_accent = VINYL_LABEL_DARK
            else:
                pygame.draw.circle(surf, VINYL_LABEL, center, label_r)
                label_accent = VINYL_LABEL_DARK

            p = self.settings
            vertical = text_mode in ('straight', 'blocky')
            # Don't scribble fake chickenscratch over an image label; real text
            # (when there's metadata) and decorations are fine everywhere.
            if artist or album or not is_image:
                artist_col = _resolve_color(p.artist_color, label_accent)
                album_col = _resolve_color(p.album_color, label_accent)
                self._draw_label_text(surf, size, size, label_r, label_accent,
                                      artist, album, text_mode, text_font,
                                      artist_col, album_col)
            d1, d2 = p.decor1, p.decor2
            if (d1 and d1 != 'none') or (d2 and d2 != 'none'):
                slots = [
                    (d1, _resolve_color(p.decor1_color, label_accent)),
                    (d2, _resolve_color(p.decor2_color, label_accent)),
                ]
                seed = abs(hash(album_path or '')) % (1 << 30)
                self._draw_label_decor(surf, size, size, label_r, slots, seed, vertical)

        # Spindle hole
        pygame.draw.circle(surf, DARK_BG, center, int(size * 0.04))

        # Brightness adjustment
        brightness = self.settings.brightness
        if brightness < 100:
            alpha = int(255 * (1 - brightness / 100))
            dim = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(dim, (0, 0, 0, alpha), center, size)
            surf.blit(dim, (0, 0))

        return surf

    def build_grooves_overlay(self, size, style, boundaries, album_dur):
        """Build the music-zone overlay with track-boundary gaps.

        Returns (surface, blend_mode) where blend_mode is 'blend' (normal alpha)
        for a darkening haze on light vinyls, or 'add' for an additive shine on
        patterned and dark vinyls. Shine renders consistently regardless of
        whatever the body texture is underneath — additive light always brightens.
        """
        d = size * 2
        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        center = (size, size)

        if not style:
            style = {'type': 'black'}
        style_type = style.get('type', 'black')

        overlay_c = None
        blend_mode = 'blend'

        if style_type == 'clear':
            # Bright body — additive shine makes grooves read as highlights
            # catching the light, not as washed-out haze.
            overlay_c = CLEAR_GROOVE_COLORS[0]
            blend_mode = 'add'
        elif style_type == 'color':
            overlay_c = VINYL_GROOVE_COLORS.get(
                style.get('color', ''), ((0, 0, 0, 28), None))[0]
            # Dark bodies get a light shine (additive); light bodies get a
            # dark haze (normal alpha blend).
            if overlay_c and overlay_c[0] > 128:  # light overlay color
                blend_mode = 'add'
        elif style_type == 'black':
            # Darker bands in the music zone — grooves cast deeper shadows
            # than the smooth lead-in flats. Normal alpha blend.
            overlay_c = (0, 0, 0, 25)
        elif style_type == 'munafo':
            variant = style.get('variant')
            cfg_name = variant[0] if variant else None
            overlay_c = MUNAFO_GROOVE_COLORS.get(cfg_name, ((0, 0, 0, 30), None))[0]
            blend_mode = 'add' if overlay_c[0] > 128 else 'blend'
        elif style_type == 'pattern':
            # Inherit groove behavior from the underlying fractal type.
            sub = style.get('sub') or {}
            sub_type = sub.get('type')
            if sub_type == 'munafo':
                variant = sub.get('variant')
                cfg_name = variant[0] if variant else None
                overlay_c = MUNAFO_GROOVE_COLORS.get(cfg_name, ((0, 0, 0, 30), None))[0]
                blend_mode = 'add' if overlay_c[0] > 128 else 'blend'
            else:
                overlay_c = (255, 255, 255, 45)
                blend_mode = 'add'
        elif style_type in ('mandelbrot', 'nebula', 'picture'):
            overlay_c = (255, 255, 255, 45)
            blend_mode = 'add'

        if overlay_c is not None:
            self._draw_music_zones(surf, size, center, overlay_c,
                                   boundaries=boundaries, album_dur=album_dur,
                                   gap_half_width=2)

        brightness = self.settings.brightness
        if brightness < 100:
            arr = pygame.surfarray.pixels_alpha(surf)
            arr[:] = (arr.astype(np.float32) * brightness / 100).astype(np.uint8)
            del arr

        return surf, blend_mode

    # Screen-fixed specular shine. Drawn at a CONSTANT angle on top of the
    # rotating body + grooves, so the room-light reflection stays put while the
    # record spins — light doesn't rotate with the disc. White + additive, so
    # it reads as a highlight over any body color/art/fractal.
    # A narrow specular streak, alpha-blended toward white (NOT additive, so it
    # never blows out a bright body like the clear platter). Fixed in screen
    # space and applied to all styles.
    _SHINE_PARAMS = dict(
        streak_x_frac     = -0.05,
        streak_angle_deg  = 15.0,   # 11:30→5:30 tilt (slight top-left lean)
        streak_core_width = 0.06,   # tight bright core
        streak_core_alpha = 0.28,
        streak_halo_width = 0.16,   # modest soft halo
        streak_halo_alpha = 0.10,
    )

    # Per-style streak overrides for the shared shine overlay. Currently empty —
    # clear vinyl owns its specular streak inside _draw_clear_vinyl so the light
    # rotates with the disc and reads as "from within", and every other style is
    # happy with _SHINE_PARAMS.
    _SHINE_OVERRIDES_BY_TYPE = {}

    # Per-style gloss: vinyl is glossy across the board, but album-art /
    # fractal faces get a lighter touch so detail isn't blown out. Clear is 0
    # because its streak is drawn inside the rotating disc body (see
    # _draw_clear_vinyl), not as a screen-fixed reflection.
    _GLOSS_BY_TYPE = {
        'clear': 0.0, 'color': 0.95, 'black': 0.7,
        'mandelbrot': 0.7, 'nebula': 0.7, 'munafo': 0.7,
        'picture': 0.55, 'pattern': 0.65,
    }

    def build_shine_overlay(self, size, style):
        """Build the fixed specular shine overlay (white RGBA, additive blend).

        Returns a surface to draw at angle=0 over the spinning record.
        """
        style_type = (style or {}).get('type', 'black')
        p = {**self._SHINE_PARAMS, **self._SHINE_OVERRIDES_BY_TYPE.get(style_type, {})}
        gloss = self._GLOSS_BY_TYPE.get(style_type, 0.7)
        d = size * 2
        cx = cy = size

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        in_disc = np.clip(size - r + 0.5, 0.0, 1.0)

        # Tilted specular streak (window reflection) — broad core + wide halo,
        # full-height column (matches the original clear-vinyl streak).
        ang = np.deg2rad(p['streak_angle_deg'])
        u = (dx - size * p['streak_x_frac']) * np.cos(ang) - dy * np.sin(ang)
        core = np.exp(-(u / (size * p['streak_core_width'])) ** 2) * p['streak_core_alpha']
        halo = np.exp(-(u / (size * p['streak_halo_width'])) ** 2) * p['streak_halo_alpha']
        streak = core + halo

        alpha_frac = np.clip(streak * gloss, 0.0, 1.0) * in_disc

        # Don't shine over the center label — it's paper, not glossy vinyl.
        # Picture / pattern discs have no label (body runs edge-to-edge).
        if (style or {}).get('type', 'black') not in ('picture', 'pattern'):
            label_r = size * LABEL_RADIUS
            outside_label = np.clip(r - label_r + 0.5, 0.0, 1.0)
            alpha_frac = alpha_frac * outside_label

        brightness = self.settings.brightness
        if brightness < 100:
            alpha_frac = alpha_frac * (brightness / 100.0)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = 255
        rgba[..., 1] = 255
        rgba[..., 2] = 255
        rgba[..., 3] = (alpha_frac * 255.0).astype(np.uint8)

        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0))
        return surf

    @staticmethod
    def _draw_specular_highlight(surf, size, center, color, highlight_angle=-np.pi * 0.35):
        """Render a single angular specular highlight — a soft bright crescent
        on one side of the disc, suggesting overhead light reflection.
        """
        d = size * 2
        cx = d // 2
        cy = d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        theta = np.arctan2(dy, dx)

        # Soft-edged disc mask.
        in_disc = np.clip(size - r + 0.5, 0.0, 1.0)

        # Angular intensity: smooth crescent peaking at highlight_angle.
        phase = np.cos(theta - highlight_angle)
        angular = np.maximum(phase, 0.0) ** 2

        alpha_frac = in_disc * angular

        alpha_val = color[3] if len(color) == 4 else 255
        alpha = (alpha_frac * alpha_val).astype(np.uint8)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = color[0]
        rgba[..., 1] = color[1]
        rgba[..., 2] = color[2]
        rgba[..., 3] = alpha

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    @staticmethod
    def _draw_music_zones(surf, size, center, color, boundaries=None,
                          album_dur=None, gap_half_width=2):
        """Render the music-groove zones as a hazy color overlay with track gaps."""
        d = size * 2
        r_inner = size * INNER_GROOVE
        r_outer = size * OUTER_GROOVE
        cx = d // 2
        cy = d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)

        # Soft-edged annular band (1-px AA falloff at the band's inner/outer edge).
        alpha_frac = np.clip(r - r_inner, 0.0, 1.0) * np.clip(r_outer - r, 0.0, 1.0)

        # Carve gaps at each track boundary with 1-px soft edges.
        if boundaries and album_dur and album_dur > 0:
            groove_range = (OUTER_GROOVE - INNER_GROOVE) * size
            for b in boundaries[1:]:
                frac = b / album_dur
                r_boundary = size * OUTER_GROOVE - frac * groove_range
                gap_factor = np.clip(np.abs(r - r_boundary) - (gap_half_width - 1),
                                     0.0, 1.0)
                alpha_frac = alpha_frac * gap_factor

        alpha_val = color[3] if len(color) == 4 else 255
        alpha = (alpha_frac * alpha_val).astype(np.uint8)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = color[0]
        rgba[..., 1] = color[1]
        rgba[..., 2] = color[2]
        rgba[..., 3] = alpha

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    @staticmethod
    def _draw_grooves(surf, size, center, color, spacing=3, ss_factor=None,
                      boundaries=None, album_dur=None, gap_half_width=2):
        """Draw the record's groove as a single continuous spiral, with subpixel AA.

        Real LP grooves are a spiral. Rotation has a visible effect. `spacing`
        is the spiral pitch (radial advance per turn) at display resolution.

        At each track boundary, the spiral is suppressed in a small radial band:
        on a real LP these are flat (musicless) lead-in grooves between tracks,
        which read visually as the boundary marker.
        """
        if ss_factor is None:
            ss_factor = RECORD_SUPERSAMPLE
        d = size * 2
        pitch = spacing * ss_factor
        r_inner = size * INNER_GROOVE
        r_outer = size * OUTER_GROOVE
        cx = d // 2
        cy = d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        theta = np.arctan2(dy, dx)

        in_band = (r >= r_inner) & (r <= r_outer)

        # Radial distance to nearest spiral arm.
        spiral_phase = (2 * np.pi / pitch) * r
        diff = np.mod(theta - spiral_phase, 2 * np.pi)
        mod_phase = np.minimum(diff, 2 * np.pi - diff)
        radial_dist = mod_phase * pitch / (2 * np.pi)

        # 1-display-px stroke = ss_factor surface px.
        half_stroke = ss_factor / 2.0
        alpha_frac = np.clip(half_stroke + 0.5 - radial_dist, 0.0, 1.0)

        # Suppress the spiral inside each track-boundary gap.
        if boundaries and album_dur and album_dur > 0:
            groove_range = (OUTER_GROOVE - INNER_GROOVE) * size
            gap_half = gap_half_width * ss_factor
            for b in boundaries[1:]:
                frac = b / album_dur
                r_boundary = size * OUTER_GROOVE - frac * groove_range
                in_gap = np.abs(r - r_boundary) < gap_half
                alpha_frac = np.where(in_gap, 0.0, alpha_frac)

        alpha_val = color[3] if len(color) == 4 else 255
        alpha = (in_band * alpha_frac * alpha_val).astype(np.uint8)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = color[0]
        rgba[..., 1] = color[1]
        rgba[..., 2] = color[2]
        rgba[..., 3] = alpha

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    def _draw_black_vinyl(self, surf, size, center):
        """Draw a plain black vinyl base disc (grooves go on the overlay)."""
        base, _, _ = VINYL_BLACK
        pygame.draw.circle(surf, base, center, size)

    # Colored-vinyl body. Flat fill reads dull, so we brighten the pigment and
    # add a radial rim vignette for a domed look. Both are rotation-invariant
    # (the directional/specular "shine" is a separate fixed overlay — see
    # _build_shine_overlay — so light doesn't spin with the disc).
    _COLOR_PARAMS = dict(
        lift        = 0.18,   # brighten body toward white (overall pop)
        edge_darken = 0.20,   # vignette at the rim for a domed look
    )

    def _draw_color_vinyl(self, surf, size, center, base, **overrides):
        """Draw a brightened colored-vinyl base disc (radial shading only)."""
        p = {**self._COLOR_PARAMS, **overrides}
        d = size * 2
        cx, cy = d // 2, d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        in_disc = np.clip(size - r + 0.5, 0.0, 1.0)
        rr = np.clip(r / size, 0.0, 1.0)

        base = np.array(base, dtype=np.float32)
        # Brighten the body toward white — lifts dull colors without hue shift
        # and never clips (channels already near 255 barely move).
        body = base + (255.0 - base) * p['lift']

        # Radial vignette only — darken toward the rim for depth.
        shade = 1.0 - p['edge_darken'] * rr ** 3

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = np.clip(body[0] * shade, 0, 255).astype(np.uint8)
        rgba[..., 1] = np.clip(body[1] * shade, 0, 255).astype(np.uint8)
        rgba[..., 2] = np.clip(body[2] * shade, 0, 255).astype(np.uint8)
        rgba[..., 3] = (in_disc * 255.0).astype(np.uint8)

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    # Tunable knobs for the clear-vinyl look. Each parameter is independent
    # so we can dial them one at a time.
    _CLEAR_PARAMS = dict(
        # --- Platter / disc body. We can't lighten the player UI bg, so
        # the disc itself carries the silver/white weight. Near-opaque
        # silver so it reads as "clear vinyl on a light surface" against
        # any background.
        platter_color        = (210, 215, 220),  # silver-white
        platter_alpha        = 0.92,
        body_alpha           = 0.03,
        # --- Specular streak (vertical window-reflection column).
        # SOFT and WIDE — reference shows a broad luminous column, not a
        # hard narrow band.
        streak_x_frac        = -0.05,
        streak_angle_deg     = -4.0,
        streak_core_width    = 0.13,   # broad bright core
        streak_core_alpha    = 0.45,   # lower since base is already bright
        streak_halo_width    = 0.45,   # very wide soft halo
        streak_halo_alpha    = 0.35,
        streak_top_fade      = 0.0,
        # --- Concentric groove striations across the disc face ---
        striation_alpha      = 0.30,
        striation_freq       = 0.45,
        # --- Rainbow refraction (more visible now that platter is bright) ---
        rainbow_strength     = 0.80,
        # --- Rim ---
        rim_alpha            = 0.55,
        rim_width_px         = 2.5,
    )

    def _draw_clear_vinyl(self, surf, size, center, **overrides):
        """Draw a clear-vinyl base disc with platter + shimmer.

        Layers (back-to-front):
          1. Silver platter — gives the disc weight against the dark UI
             background so the clear vinyl reads as "sitting on a
             turntable" rather than "ghost".
          2. Body — slight overall brightness on top of the platter.
          3. Specular streak — bright Gaussian CORE + wider HALO, slightly
             tilted, fading top-to-bottom (light from above). Clear vinyl
             intentionally bakes its streak into the rotating disc body
             (rather than the screen-fixed shine overlay used by every other
             style) — this combined-pass look is what gives it its glow.
          4. Groove shimmer — subtle concentric brighter bands in the
             music zone where light catches groove ridges.
          5. Rim — bright edge highlight.

        Pass keyword overrides to tweak per-call:
            self._draw_clear_vinyl(surf, size, center, streak_core_alpha=0.9)
        """
        p = {**self._CLEAR_PARAMS, **overrides}

        d = size * 2
        cx, cy = d // 2, d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)
        in_disc = np.clip(size - r + 0.5, 0.0, 1.0)

        # 1+2. Platter (silver base) + faint body on top, as a single layer.
        platter_a = in_disc * p['platter_alpha']
        body_a = in_disc * p['body_alpha']

        pc = np.array(p['platter_color'], dtype=np.float32)

        # 3. Streak (rotated)
        ang = np.deg2rad(p['streak_angle_deg'])
        u = (dx - size * p['streak_x_frac']) * np.cos(ang) - dy * np.sin(ang)
        core_sigma = size * p['streak_core_width']
        halo_sigma = size * p['streak_halo_width']
        core = np.exp(-(u / core_sigma) ** 2) * p['streak_core_alpha']
        halo = np.exp(-(u / halo_sigma) ** 2) * p['streak_halo_alpha']
        vfade = np.clip((size - dy) / (2 * size), 0.0, 1.0) ** p['streak_top_fade']
        streak = (core + halo) * vfade * in_disc

        # 4. Concentric groove striations — visible across the whole disc
        # face (not just the music zone), modulating sinusoidally on r.
        # Strongest in the mid-radius where light has the most surface area
        # to catch, falling off near center and edge.
        radial_env = np.clip(in_disc, 0.0, 1.0) * np.clip(r / size, 0.0, 1.0)
        striations = (0.5 + 0.5 * np.sin(r * p['striation_freq'])) * radial_env * p['striation_alpha']

        # 5. Rim
        rim = np.clip(1.0 - np.abs(r - (size - 1.5)) / p['rim_width_px'],
                      0.0, 1.0) * p['rim_alpha']

        white_a = np.clip(body_a + streak + striations + rim, 0.0, 1.0)

        # --- Rainbow refraction tints ---
        # Where light catches the grooves it doesn't read as pure white —
        # plastic refracts wavelengths slightly differently, giving an
        # iridescent shimmer. We modulate a HSV hue with r and apply it
        # at low saturation, scaled to the striation strength so it only
        # shows where light is actually catching.
        hue = (r * p['striation_freq'] * 0.10) % 1.0
        # HSV → RGB with low saturation. Cheap inline conversion:
        i = (hue * 6.0).astype(np.int32) % 6
        f = hue * 6.0 - (hue * 6.0).astype(np.int32)
        # Saturated rainbow channels (sat=1, val=1).
        rb_r = np.where(i == 0, 1.0,
              np.where(i == 1, 1 - f,
              np.where(i == 2, 0.0,
              np.where(i == 3, 0.0,
              np.where(i == 4, f, 1.0)))))
        rb_g = np.where(i == 0, f,
              np.where(i == 1, 1.0,
              np.where(i == 2, 1.0,
              np.where(i == 3, 1 - f,
              np.where(i == 4, 0.0, 0.0)))))
        rb_b = np.where(i == 0, 0.0,
              np.where(i == 1, 0.0,
              np.where(i == 2, f,
              np.where(i == 3, 1.0,
              np.where(i == 4, 1.0, 1 - f)))))
        # Iridescence weight — only where the striations are catching light.
        irid_w = striations * p['rainbow_strength']
        # Mix the rainbow color into the white-highlight color.
        hi_r = 255.0 * (1 - irid_w) + (rb_r * 255.0) * irid_w
        hi_g = 255.0 * (1 - irid_w) + (rb_g * 255.0) * irid_w
        hi_b = 255.0 * (1 - irid_w) + (rb_b * 255.0) * irid_w

        # Composite — platter base lightened toward (white/iridescent) by
        # the white_a alpha.
        r_arr = pc[0] * (1.0 - white_a) + hi_r * white_a
        g_arr = pc[1] * (1.0 - white_a) + hi_g * white_a
        b_arr = pc[2] * (1.0 - white_a) + hi_b * white_a
        alpha = np.maximum(platter_a, white_a) * 255.0

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = np.clip(r_arr, 0, 255).astype(np.uint8)
        rgba[..., 1] = np.clip(g_arr, 0, 255).astype(np.uint8)
        rgba[..., 2] = np.clip(b_arr, 0, 255).astype(np.uint8)
        rgba[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    def _draw_track_marks(self, surf, size, center, color, boundaries, album_dur, ss_factor=None):
        """Draw track boundary rings at album track positions, with subpixel AA.

        Track marks remain concentric circles (one per track) — they're not part
        of the spiral, they mark where one track ends and the next begins.
        Each ring is 1 display pixel wide.
        """
        if not (album_dur > 0 and boundaries):
            return
        if ss_factor is None:
            ss_factor = RECORD_SUPERSAMPLE

        d = size * 2
        groove_range = (OUTER_GROOVE - INNER_GROOVE) * size
        cx = d // 2
        cy = d // 2

        py, px = np.mgrid[0:d, 0:d].astype(np.float32)
        dx = px - cx
        dy = py - cy
        r = np.sqrt(dx * dx + dy * dy)

        # 2-display-px stroke (visibly heavier than the 1-px spiral, but
        # not "huge"). half_stroke=0.5 + the +0.5 in the formula = 2px wide.
        ring_half_stroke = ss_factor * 0.5

        alpha_frac = np.zeros_like(r)
        for b in boundaries[1:]:
            frac = b / album_dur
            r_ring = size * OUTER_GROOVE - frac * groove_range
            ring_alpha = np.clip(ring_half_stroke - np.abs(r - r_ring) + 0.5, 0.0, 1.0)
            alpha_frac = np.maximum(alpha_frac, ring_alpha)

        alpha_val = color[3] if len(color) == 4 else 255
        alpha = (alpha_frac * alpha_val).astype(np.uint8)

        rgba = np.empty((d, d, 4), dtype=np.uint8)
        rgba[..., 0] = color[0]
        rgba[..., 1] = color[1]
        rgba[..., 2] = color[2]
        rgba[..., 3] = alpha

        overlay = pygame.image.frombuffer(rgba.tobytes(), (d, d), 'RGBA').copy()
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)

    @staticmethod
    def _blit_disc_fill(surf, size, img):
        """Blit a prerendered fractal disc so it fills the full record radius.

        The cached patterns leave a transparent margin (the disc is masked at
        ~0.95–0.97 of the frame, and it differs per pattern family). Auto-detect
        each disc's actual opaque extent and scale so it reaches radius `size`,
        then mask to a clean circle — so patterns match the full-size colored
        and album-art discs regardless of their individual inset.
        """
        d = size * 2
        bb = img.get_bounding_rect(min_alpha=1)
        if bb.width > 0 and bb.height > 0:
            iw, ih = img.get_size()
            scale = d / max(bb.width, bb.height)
            scaled = pygame.transform.smoothscale(
                img, (max(1, round(iw * scale)), max(1, round(ih * scale))))
            # Map the opaque bbox center onto the disc center.
            ox = round(size - (bb.x + bb.width / 2.0) * scale)
            oy = round(size - (bb.y + bb.height / 2.0) * scale)
            surf.blit(scaled, (ox, oy))
        else:
            surf.blit(pygame.transform.smoothscale(img, (d, d)), (0, 0))

        # Clean circular edge at the full radius (also crops any overscan).
        mask = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (size, size), size)
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    def _draw_mandelbrot_vinyl(self, surf, size, center, variant):
        """Draw a vinyl with a Mandelbrot set pattern. Uses pre-rendered cache if available."""
        name = variant[4]
        color = variant[5]
        cache_path = os.path.join(CACHE_DIR, f'{name}-{color}.png')

        if os.path.isfile(cache_path):
            img = pygame.image.load(cache_path)
        else:
            img = _render_mandelbrot_surface(variant, size)

        self._blit_disc_fill(surf, size, img)

    def _draw_munafo_vinyl(self, surf, size, center, variant):
        """Draw a vinyl with a Munafo deep-zoom pattern. Uses the 1600x1600
        pre-rendered cache; falls back to downsampling the 9000x9000 gold
        archive on the fly if the cache is missing (slow first frame)."""
        config_name = variant[0]
        cache_path = os.path.join(MUNAFO_CACHE_DIR, f'{config_name}.png')

        if os.path.isfile(cache_path):
            img = pygame.image.load(cache_path)
        else:
            img = _render_munafo_surface(variant, size)

        self._blit_disc_fill(surf, size, img)

    def _draw_nebula_vinyl(self, surf, size, center, variant):
        """Draw a vinyl with a nebula pattern. Uses pre-rendered cache if available."""
        name = variant[2]
        cache_path = os.path.join(NEBULA_CACHE_DIR, f'{name}.png')

        if os.path.isfile(cache_path):
            img = pygame.image.load(cache_path)
        else:
            img = _render_nebula_surface(variant, size)

        self._blit_disc_fill(surf, size, img)
