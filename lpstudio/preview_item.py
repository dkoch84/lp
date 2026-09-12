"""MandelPreviewItem — the live spinning-vinyl preview for lp-studio.

A QML-registered QQuickPaintedItem bound to the StudioController. On any param
change it re-renders (debounced) the full vinyl through ``studio.render_vinyl``
— body + grooves composited into one disc that *rotates*, plus a screen-fixed
specular shine drawn on top. Same compositing/blend rules as lp-deck's
VinylItem, so the preview matches production 1:1. pygame runs headless (SDL
dummy) purely to rasterize.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PySide6.QtCore import Property, QObject, QRectF, QTimer, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQuick import QQuickPaintedItem

from . import studio

_PYGAME_READY = False

# Internal render radius (disc is 2×). High enough to stay crisp scaled up to a
# large preview pane; downscaling on the GPU is sharp. Production caches at 800.
RENDER_R = 480
DEG_PER_FRAME = 0.8     # lp's gentle ~4 RPM screen spin


def _ensure_pygame():
    global _PYGAME_READY
    if not _PYGAME_READY:
        pygame.init()
        pygame.font.init()
        _PYGAME_READY = True


def _surface_to_qimage(surf):
    w, h = surf.get_size()
    data = pygame.image.tobytes(surf, "RGBA")
    return QImage(data, w, h, QImage.Format_RGBA8888).copy()


class MandelPreviewItem(QQuickPaintedItem):
    controllerChanged = Signal()
    spinningChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        _ensure_pygame()
        self._controller = None
        self._disc = None       # body + grooves (rotates)
        self._shine = None      # specular streak (drawn fixed)
        self._angle = 0.0
        self._spinning = True
        self.setAntialiasing(True)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(80)
        self._debounce.timeout.connect(self._render)

        self._spin = QTimer(self)
        self._spin.setInterval(33)      # ~30fps
        self._spin.timeout.connect(self._tick)
        self._spin.start()

    # --- controller binding ---

    def getController(self):
        return self._controller

    def setController(self, c):
        self._controller = c
        if c is not None:
            c.paramsChanged.connect(self._debounce.start)
            self._render()

    controller = Property(QObject, getController, setController,
                          notify=controllerChanged)

    # --- spin toggle (QML-bindable) ---

    def getSpinning(self):
        return self._spinning

    def setSpinning(self, on):
        if on == self._spinning:
            return
        self._spinning = on
        self.spinningChanged.emit()
        self.update()

    spinning = Property(bool, getSpinning, setSpinning, notify=spinningChanged)

    # --- render ---

    def _render(self):
        if self._controller is None:
            return
        family, params, advanced = self._controller.snapshot()
        body, grooves, blend, shine = studio.render_vinyl(
            params, family, advanced, RENDER_R)
        disc = _surface_to_qimage(body)
        p = QPainter(disc)
        # premultiplied add == SDL BLENDMODE_ADD; SourceOver == BLENDMODE_BLEND
        p.setCompositionMode(QPainter.CompositionMode_Plus if blend == "add"
                             else QPainter.CompositionMode_SourceOver)
        p.drawImage(0, 0, _surface_to_qimage(grooves))
        p.end()
        self._disc = disc
        self._shine = _surface_to_qimage(shine)
        self.update()

    def _tick(self):
        if self._spinning and self._disc is not None:
            self._angle = (self._angle + DEG_PER_FRAME) % 360
            self.update()

    def paint(self, p):
        if self._disc is None:
            return
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        side = min(self.width(), self.height())
        dst = QRectF((self.width() - side) / 2, (self.height() - side) / 2,
                     side, side)
        p.translate(dst.center())
        p.rotate(self._angle)
        p.translate(-dst.center())
        p.drawImage(dst, self._disc, QRectF(self._disc.rect()))
        p.resetTransform()
        if self._shine is not None:
            p.drawImage(dst, self._shine, QRectF(self._shine.rect()))
