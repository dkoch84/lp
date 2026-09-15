"""Tests for lp-studio's value boxes: exact values without dragging a slider.

Every slider has a box beside it showing its value. Typing a number and
pressing Enter sets it exactly (a slider alone can't reliably land on 14 out of
255), Up/Down nudge by one step and Shift by ten, and out-of-range or junk input
can't push a bad value into the renderer. These drive the real QML.

    .venv/bin/python -m pytest tests/test_studio_controls.py
"""
import os
import sys

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip('PySide6', reason='lp-studio needs PySide6 (requirements-deck.txt)')

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from lpstudio import studio
from lpstudio.__main__ import build_engine
from lpstudio.preview_item import MandelPreviewItem


@pytest.fixture(scope='module')
def ui(tmp_path_factory):
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = studio.StudioController()
    controller.setFamily('smoke')
    settings = tmp_path_factory.mktemp('studio-settings') / 'studio.ini'
    engine = build_engine(controller, settings_file=str(settings))
    win = engine.rootObjects()[0]
    app.processEvents()
    # colours show as a swatch; their channel boxes are one click away
    next(i for i in _items(win.contentItem())
         if i.objectName() == 'channels_smk_acc_ink').setProperty('checked', True)
    app.processEvents()
    yield app, win, controller
    for item in win.findChildren(MandelPreviewItem):
        item.shutdown()


def _items(item):
    yield item
    for child in item.childItems():
        yield from _items(child)


def _box(win, key):
    """The value box of the control for `key`. Walks the visual item tree:
    Repeater delegates are not reliably in the QObject tree findChildren uses."""
    for box in _items(win.contentItem()):
        if box.objectName() != 'valueBox':
            continue
        control = box.parentItem()
        while control is not None and not control.property('spec'):
            control = control.parentItem()
        if control is not None and control.property('spec').get('key') == key:
            return box
    raise LookupError(f'no value box for {key}')


def _type(ui, key, text):
    app, win, c = ui
    box = _box(win, key)
    box.forceActiveFocus()
    box.setProperty('text', text)
    QTest.keyClick(win, Qt.Key_Return)
    app.processEvents()
    return c.param(key)


def _press(ui, key, k, mods=Qt.NoModifier):
    app, win, c = ui
    _box(win, key).forceActiveFocus()
    QTest.keyClick(win, k, mods)
    app.processEvents()
    return c.param(key)


def test_typing_sets_an_exact_integer(ui):
    assert _type(ui, 'smk_acc_ink_r', '14') == 14


def test_arrows_nudge_by_one_step_and_shift_by_ten(ui):
    _type(ui, 'smk_acc_ink_r', '14')
    assert _press(ui, 'smk_acc_ink_r', Qt.Key_Up) == 15
    assert _press(ui, 'smk_acc_ink_r', Qt.Key_Up, Qt.ShiftModifier) == 25
    assert _press(ui, 'smk_acc_ink_r', Qt.Key_Down) == 24


def test_typing_sets_an_exact_decimal(ui):
    assert _type(ui, 'smk_acc_amount', '0.123') == pytest.approx(0.123)


def test_out_of_range_is_clamped_to_the_slider(ui):
    assert _type(ui, 'smk_acc_ink_r', '300') == 255
    assert _type(ui, 'smk_acc_ink_r', '-5') == 0


def test_junk_keeps_the_value_and_restores_the_box(ui):
    _app, win, _c = ui
    _type(ui, 'smk_acc_amount', '0.2')
    assert _type(ui, 'smk_acc_amount', 'abc') == pytest.approx(0.2)
    assert _box(win, 'smk_acc_amount').property('text') == '0.2'


def test_box_follows_changes_made_elsewhere(ui):
    app, win, c = ui
    win.contentItem().forceActiveFocus()     # no box is being edited
    c.setParam('smk_acc_ink_g', 77)
    app.processEvents()
    assert _box(win, 'smk_acc_ink_g').property('text') == '77'
