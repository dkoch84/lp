"""VinylItem — the spinning lp vinyl as a Qt Quick item (req #6).

A QML-registered QQuickPaintedItem that reuses lpcore.vinyl.VinylRenderer (the
kiosk's exact renderer): build body + grooves + shine as pygame surfaces once per
album, then spin in a QTimer — rotate the cached disc each frame, draw the
specular shine fixed. Identical pipeline to the legacy `vinyl_widget`, repackaged
for the scene graph.

It drives itself off the Controller: set `controller`, and it rebuilds + spins on
each now-playing change. pygame runs headless (SDL dummy) purely to rasterize.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PySide6.QtCore import Property, QObject, QRectF, QTimer, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQuick import QQuickPaintedItem

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


RENDER_R = 480               # internal render radius (quality knob; item scales it)
# lp's display.py spins the record at +0.8°/frame @ 30fps (~4 RPM): a slow,
# pleasant turn — NOT real 33⅓ RPM, which reads as frantic on screen.
DEG_PER_FRAME = 0.8


def composite_disc(renderer, size, boundaries, album_dur, art_path=None,
                   album_path=None, artist=None, album=None, with_shine=True):
    """Composite body + grooves into one QImage, matching lp's SDL blending 1:1.

    lp (display.py) uploads the grooves as an SDL texture and draws it with
    BLENDMODE_ADD / BLENDMODE_BLEND — SDL premultiplies the source by its alpha
    before adding, so faint grooves stay subtle. pygame's BLEND_RGBA_ADD does
    NOT premultiply (it adds raw RGB), which blows the grooves out far too
    bright. QPainter composites in premultiplied space, so CompositionMode_Plus
    reproduces BLENDMODE_ADD exactly, and SourceOver matches BLENDMODE_BLEND.
    Returns (disc_qimage, shine_qimage|None).
    """
    style = renderer.get_vinyl_style(album_path)
    body = renderer.build_record(size, boundaries, album_dur, art_path,
                                 album_path, artist, album)
    grooves, blend = renderer.build_grooves_overlay(size, style, boundaries, album_dur)
    disc = _surface_to_qimage(body)
    p = QPainter(disc)
    p.setCompositionMode(QPainter.CompositionMode_Plus if blend == "add"
                         else QPainter.CompositionMode_SourceOver)
    p.drawImage(0, 0, _surface_to_qimage(grooves))
    p.end()
    shine = (_surface_to_qimage(renderer.build_shine_overlay(size, style))
             if with_shine else None)
    return disc, shine


class VinylItem(QQuickPaintedItem):
    controllerChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        _ensure_pygame()
        self._settings = VinylSettings()
        self._renderer = VinylRenderer(self._settings)
        self._disc = None       # QImage: body + grooves (rotates)
        self._shine = None      # QImage: specular streak (drawn fixed)
        self._angle = 0.0
        self._spinning = False
        self._controller = None
        self.setAntialiasing(True)
        self._timer = QTimer(self)
        self._timer.setInterval(33)   # ~30fps
        self._timer.timeout.connect(self._tick)

    # --- QML property: the Controller drives the look + spin ---

    def getController(self):
        return self._controller

    def setController(self, c):
        self._controller = c
        if c is not None:
            c.nowPlayingChanged.connect(self._on_now_playing)
            c.vinylChanged.connect(self._on_now_playing)
            self._on_now_playing()

    # notify declared (never fires — the controller is set once) so QML treats
    # the property as bindable and doesn't warn / loop on `controller: controller`
    controller = Property(QObject, getController, setController,
                          notify=controllerChanged)

    def _on_now_playing(self):
        c = self._controller
        if c is None:
            return
        backend = c.player.backend
        st = backend.get_status()
        if not st.get("playing"):
            self.set_spinning(False)
            return
        spec = c.vinyl_now()             # current track's album context (+ playlist)
        if spec and spec["album_path"]:
            self.set_settings(spec["settings"])
            self.set_album(spec["album_path"], list(backend.track_boundaries),
                           backend.album_duration, spec["art_path"],
                           spec["artist"], spec["album"])
        self.set_spinning(True)

    # --- build / state ---

    def set_settings(self, settings):
        self._settings = settings
        self._renderer = VinylRenderer(settings)

    def set_album(self, album_path, boundaries, album_dur, art_path=None,
                  artist=None, album=None):
        self._disc, self._shine = composite_disc(
            self._renderer, RENDER_R, boundaries, album_dur, art_path,
            album_path, artist, album, with_shine=True)
        self.update()

    def set_spinning(self, on):
        self._spinning = on
        if on:
            self._timer.start()
        else:
            self._timer.stop()
            self.update()

    # --- render ---

    def _tick(self):
        if self._spinning:
            self._angle = (self._angle + DEG_PER_FRAME) % 360
            self.update()

    def paint(self, p):
        if self._disc is None:
            return
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        side = min(self.width(), self.height())
        dst = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        # save/restore rather than resetTransform: the painter arrives with Qt's
        # device-pixel-ratio scale already applied, and resetting drops it, which
        # drew the fixed shine at the wrong size and place on a scaled display.
        p.save()
        p.translate(dst.center())
        p.rotate(self._angle)
        p.translate(-dst.center())
        p.drawImage(dst, self._disc, QRectF(self._disc.rect()))
        p.restore()
        if self._shine is not None:
            p.drawImage(dst, self._shine, QRectF(self._shine.rect()))
