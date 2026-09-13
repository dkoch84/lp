"""MandelPreviewItem: the live spinning-vinyl preview for lp-studio.

A QML-registered QQuickPaintedItem bound to the StudioController. On any param
change it re-renders (debounced) the full vinyl through ``studio.render_vinyl``:
body + grooves composited into one disc that *rotates*, plus a screen-fixed
specular shine drawn on top. Same compositing/blend rules as lp-deck's
VinylItem, so the preview matches production 1:1. pygame runs headless (SDL
dummy) purely to rasterize.

Renders run in a separate worker process, so a slow style (layered smoke takes
seconds) never freezes the window. Changes made while a render is running are
not lost: when it finishes, the latest settings render next.
"""
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PySide6.QtCore import Property, QCoreApplication, QObject, QRectF, QTimer, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQuick import QQuickPaintedItem

from lpcore.vinyl import fractals

from . import studio

_PYGAME_READY = False

# Internal render radius (disc is 2x). High enough to stay crisp scaled up to a
# large preview pane; downscaling on the GPU is sharp. Production caches at 800.
RENDER_R = 480
DEG_PER_FRAME = 0.8     # lp's gentle ~4 RPM screen spin
# Layered smoke costs seconds per render (the time grows with the square of the
# radius), so it previews small while tuning. HQ renders large enough to judge
# its edges.
SMOKE_PREVIEW_R = 200
SMOKE_HQ_R = 400


def _ensure_pygame():
    global _PYGAME_READY
    if not _PYGAME_READY:
        pygame.init()
        pygame.font.init()
        _PYGAME_READY = True


def render_job(params, family, advanced, radius):
    """Render one preview. Runs in the worker process, so it returns plain
    picklable data: (w, h, RGBA bytes) for body, grooves and shine, plus the
    groove blend mode."""
    _ensure_pygame()
    # The worker lives as long as the app, so it can keep noise fields between
    # renders: changing a colour or opacity then skips nearly all the work.
    fractals.enable_field_cache()
    body, grooves, blend, shine = studio.render_vinyl(params, family, advanced, radius)

    def raw(surf):
        w, h = surf.get_size()
        return w, h, pygame.image.tobytes(surf, "RGBA")

    return raw(body), raw(grooves), blend, raw(shine)


def _to_qimage(raw):
    w, h, data = raw
    return QImage(data, w, h, QImage.Format_RGBA8888).copy()


class MandelPreviewItem(QQuickPaintedItem):
    controllerChanged = Signal()
    spinningChanged = Signal()
    rendered = Signal()     # a finished render reached the screen (tests wait on it)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._controller = None
        self._disc = None       # body + grooves (rotates)
        self._shine = None      # specular streak (drawn fixed)
        self._angle = 0.0
        self._spinning = True
        self.setAntialiasing(True)

        self._pool = None
        self._job = None        # (future, family, radius, started) while rendering
        self._stale = False     # params changed while a render was running

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(80)
        self._debounce.timeout.connect(self._render)

        self._poll = QTimer(self)
        self._poll.setInterval(30)
        self._poll.timeout.connect(self._collect)

        self._spin = QTimer(self)
        self._spin.setInterval(33)      # ~30fps
        self._spin.timeout.connect(self._tick)
        self._spin.start()

        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    # --- controller binding ---

    def getController(self):
        return self._controller

    def setController(self, c):
        self._controller = c
        if c is not None:
            c.paramsChanged.connect(self._schedule)
            c.hqChanged.connect(self._schedule)
            self._render()

    def _schedule(self):
        # Smoke renders that reuse cached fields take a few hundredths of a second,
        # and ones that don't are coalesced (see _render), so a short settle is enough.
        slow = self._controller is not None and self._controller.getFamily() == "smoke"
        self._debounce.setInterval(120 if slow else 80)
        self._debounce.start()

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

    def _executor(self):
        if self._pool is None:
            # spawn, not fork: forking a process that is running Qt is unsafe.
            self._pool = ProcessPoolExecutor(
                max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        return self._pool

    def _render(self):
        if self._controller is None:
            return
        if self._job is not None:
            self._stale = True
            return
        family, params, advanced = self._controller.snapshot()
        radius = RENDER_R
        if family == "smoke":
            radius = SMOKE_HQ_R if self._controller.getHq() else SMOKE_PREVIEW_R
            self._controller._set_status("Rendering smoke...")
        try:
            future = self._executor().submit(render_job, params, family, advanced, radius)
        except BrokenProcessPool:
            # The worker died (killed, out of memory). Start a fresh one.
            self._discard_pool()
            future = self._executor().submit(render_job, params, family, advanced, radius)
        self._job = (future, family, radius, time.monotonic())
        self._poll.start()

    def _collect(self):
        if self._job is None or not self._job[0].done():
            return
        future, family, radius, started = self._job
        self._job = None
        self._poll.stop()
        try:
            body, grooves, blend, shine = future.result()
        except BrokenProcessPool:
            self._discard_pool()
            self._controller._set_status("Render worker stopped; restarting it")
            self._stale = True
        except Exception as e:     # a bad param combination must not kill the app
            self._controller._set_status(f"Render failed: {e}")
        else:
            if family == "smoke":
                self._controller._set_status(
                    f"Rendered at {radius}px radius in {time.monotonic() - started:.1f}s")
            disc = _to_qimage(body)
            p = QPainter(disc)
            # premultiplied add == SDL BLENDMODE_ADD; SourceOver == BLENDMODE_BLEND
            p.setCompositionMode(QPainter.CompositionMode_Plus if blend == "add"
                                 else QPainter.CompositionMode_SourceOver)
            p.drawImage(0, 0, _to_qimage(grooves))
            p.end()
            self._disc = disc
            self._shine = _to_qimage(shine)
            self.update()
            self.rendered.emit()
        if self._stale:
            self._stale = False
            self._render()

    def shutdown(self):
        """Stop the worker without waiting for a render nobody will see."""
        self._poll.stop()
        self._job = None
        self._discard_pool()

    def _discard_pool(self):
        if self._pool is not None:
            processes = list(getattr(self._pool, "_processes", {}).values())
            self._pool.shutdown(wait=False, cancel_futures=True)
            for proc in processes:
                proc.terminate()
            self._pool = None

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
