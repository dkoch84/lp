"""Image providers for lp-studio: style images cut to discs, off the UI thread.

* ``image://disc/<file path>``: a cached style image, scaled to the size QML
  asks for and cut to a disc (the compare strip and split view).
* ``image://variations/<generation>/<index>``: a colour variation's layered
  smoke, rendered small (StudioController.hueVariations keeps the variants).

Both are masked here with QPainter rather than with a shader effect in QML, so
they draw the same under software rendering and in the offscreen screenshot
harness. Qt calls requestImage on a worker thread (ForceAsynchronousImageLoading),
so neither ever blocks the window.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QBrush, QImage, QPainter
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider

from lpcore.vinyl import fractals

THUMB_R = 64            # variation disc radius; the popup shows them at 112px
DEFAULT_EDGE = 256


def disc(image, edge):
    """``image`` scaled to cover an ``edge``-pixel square and cut to a disc."""
    scaled = image.scaled(edge, edge, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QImage(edge, edge, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.translate((edge - scaled.width()) / 2, (edge - scaled.height()) / 2)
    painter.setBrush(QBrush(scaled))
    painter.drawEllipse((scaled.width() - edge) / 2, (scaled.height() - edge) / 2, edge, edge)
    painter.end()
    return out


def _blank(edge):
    img = QImage(edge, edge, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    return img


def _edge(requested_size):
    edge = max(requested_size.width(), requested_size.height())
    return edge if edge > 0 else DEFAULT_EDGE


class DiscImages(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQmlImageProviderBase.ImageType.Image,
                         QQmlImageProviderBase.Flag.ForceAsynchronousImageLoading)

    def requestImage(self, image_id, size, requested_size):
        edge = _edge(requested_size)
        source = QImage(QUrl.fromPercentEncoding(image_id.encode()))
        return _blank(edge) if source.isNull() else disc(source, edge)


class VariationImages(QQuickImageProvider):
    def __init__(self, controller):
        super().__init__(QQmlImageProviderBase.ImageType.Image,
                         QQmlImageProviderBase.Flag.ForceAsynchronousImageLoading)
        self._controller = controller

    def requestImage(self, image_id, size, requested_size):
        d = THUMB_R * 2
        gen, _, rest = image_id.partition("/")
        try:
            job = self._controller.variation_job(int(gen), int(rest.split("/")[0]))
        except ValueError:
            job = None
        if job is None:                 # a stale request from an earlier popup
            return _blank(d)
        surf = fractals._render_nebula_surface(job, THUMB_R)
        rendered = QImage(pygame.image.tobytes(surf, "RGBA"), d, d, QImage.Format_RGBA8888).copy()
        return disc(rendered, d)
