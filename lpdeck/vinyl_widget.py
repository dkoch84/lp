"""VinylWidget — the spinning lp vinyl as a Qt widget (req #6).

Reuses lpcore.vinyl.VinylRenderer (the exact renderer the kiosk uses): build the
body + grooves + shine as pygame surfaces once per album, then spin in a QTimer
— rotate the cached body+grooves each frame, draw the specular shine fixed. The
heavy build happens off the UI thread-ish (it's fast at widget sizes); per-frame
is just a rotate + blit.

pygame runs headless here (SDL dummy video) — no window, we only use it to
rasterize surfaces, which become QImages.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PySide6.QtCore import QTimer, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

from lpcore.vinyl.render import VinylRenderer
from lpcore.vinyl.settings import VinylSettings

_PYGAME_READY = False


def _ensure_pygame():
    global _PYGAME_READY
    if not _PYGAME_READY:
        pygame.init()
        pygame.font.init()
        _PYGAME_READY = True


def _surface_to_qimage(surf):
    """pygame RGBA surface → detached QImage."""
    w, h = surf.get_size()
    data = pygame.image.tobytes(surf, "RGBA")
    return QImage(data, w, h, QImage.Format_RGBA8888).copy()


# Internal render radius for the vinyl surfaces (px). The widget scales the
# result to its own size, so this is a quality/perf knob, not a layout size.
RENDER_R = 320
RPM = 33 + 1 / 3            # because of course
DEG_PER_FRAME = RPM * 360 / 60 / 30   # at ~30fps


class VinylWidget(QWidget):
    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        _ensure_pygame()
        self._settings = settings or VinylSettings()
        self._renderer = VinylRenderer(self._settings)
        self._disc = None      # QImage: body + grooves composited (rotates)
        self._shine = None     # QImage: specular streak (drawn fixed)
        self._angle = 0.0
        self._spinning = False
        self.setMinimumSize(120, 120)

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30fps
        self._timer.timeout.connect(self._tick)

    # --- public API ---

    def set_settings(self, settings):
        """Swap the vinyl look (global/artist/album override) and rebuild."""
        self._settings = settings
        self._renderer = VinylRenderer(settings)

    def set_album(self, album_path, boundaries, album_dur, art_path=None,
                  artist=None, album=None):
        """Rebuild the disc surfaces for the now-playing album."""
        r = self._renderer
        style = r.get_vinyl_style(album_path)
        body = r.build_record(RENDER_R, boundaries, album_dur, art_path,
                              album_path, artist, album)
        grooves, blend = r.build_grooves_overlay(RENDER_R, style, boundaries, album_dur)
        shine = r.build_shine_overlay(RENDER_R, style)

        disc = body.copy()
        disc.blit(grooves, (0, 0),
                  special_flags=pygame.BLEND_RGBA_ADD if blend == "add" else 0)
        self._disc = _surface_to_qimage(disc)
        self._shine = _surface_to_qimage(shine)
        self.update()

    def set_spinning(self, on):
        self._spinning = on
        if on:
            self._timer.start()
        else:
            self._timer.stop()

    # --- internals ---

    def _tick(self):
        if self._spinning:
            self._angle = (self._angle + DEG_PER_FRAME) % 360
            self.update()

    def paintEvent(self, _ev):
        if self._disc is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        side = min(self.width(), self.height())
        dst = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        src = QRectF(self._disc.rect())

        # rotate the disc about the widget centre, draw, then the fixed shine
        p.translate(dst.center())
        p.rotate(self._angle)
        p.translate(-dst.center())
        p.drawImage(dst, self._disc, src)
        p.resetTransform()
        if self._shine is not None:
            p.drawImage(dst, self._shine, QRectF(self._shine.rect()))
