"""Regression test: the fixed shine must cover the record on a scaled display.

Both lp-deck's vinyl and lp-studio's preview drew the spinning disc, then called
`resetTransform()` before drawing the shine. The painter Qt hands to paint()
already carries the display's device-pixel-ratio scale, and resetting dropped
it, so on a 2x screen the shine came out half-size in the top-left corner.

Painting through a painter pre-scaled 2x reproduces what a HiDPI window does.

    .venv/bin/python -m pytest tests/test_vinyl_shine_scaling.py
"""
import os
import sys

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip('PySide6', reason='needs PySide6 (requirements-deck.txt)')

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

LOGICAL = 200     # item size in logical pixels
SCALE = 2         # a HiDPI display


@pytest.fixture(scope='module')
def app():
    return QGuiApplication.instance() or QGuiApplication([])


def _items():
    from lpdeck.vinyl_item import VinylItem
    from lpstudio.preview_item import MandelPreviewItem
    return [VinylItem, MandelPreviewItem]


@pytest.mark.parametrize('item_cls', _items(), ids=lambda c: c.__name__)
def test_shine_fills_the_record_on_a_2x_display(app, item_cls):
    item = item_cls()
    item.setWidth(LOGICAL)
    item.setHeight(LOGICAL)
    disc = QImage(64, 64, QImage.Format_ARGB32_Premultiplied)
    disc.fill(Qt.transparent)
    shine = QImage(64, 64, QImage.Format_ARGB32_Premultiplied)
    shine.fill(QColor(255, 255, 255))
    item._disc, item._shine, item._angle = disc, shine, 30.0

    canvas = QImage(LOGICAL * SCALE, LOGICAL * SCALE, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.scale(SCALE, SCALE)          # what Qt applies for a 2x screen
    item.paint(painter)
    painter.end()

    far = LOGICAL * SCALE - 4            # bottom-right corner, only reached at full size
    assert canvas.pixelColor(far, far).alpha() == 255, 'shine lost the display scale'
    assert canvas.pixelColor(4, 4).alpha() == 255
    if hasattr(item, 'shutdown'):
        item.shutdown()
