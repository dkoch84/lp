"""Tests for lp-studio's window: the pieces that make tuning safe and quick.

The controller already knows about linked colour ramps, guardrails, undo and
shipping (tests/test_studio_guardrails.py). These drive the real Studio.qml to
check the window exposes them: it loads cleanly, filters and folds its control
groups, takes a typed hex colour, undoes from the keyboard, shows a chip per
guardrail, hides layers that don't exist, refuses a built-in name in the Ship
dialog, and keeps lp-deck's colours.

    .venv/bin/python -m pytest tests/test_studio_window.py
"""
import os
import re
import sys

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pytest.importorskip('PySide6', reason='lp-studio needs PySide6 (requirements-deck.txt)')

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from lpcore.vinyl import ramp
from lpstudio import studio
from lpstudio.__main__ import build_engine
from lpstudio.preview_item import MandelPreviewItem

PURPLE_FIRST = ((61, 56, 167), (72, 53, 189), (75, 51, 198), (218, 195, 190))
_TOKEN = re.compile(r'readonly property color (\w+):\s*dark \? "(#[0-9A-Fa-f]{6})" : "(#[0-9A-Fa-f]{6})"')


def _tokens(path):
    with open(path) as f:
        return {name: (d.lower(), l.lower()) for name, d, l in _TOKEN.findall(f.read())}


def test_theme_keeps_lp_decks_colours():
    deck = _tokens(os.path.join(ROOT, 'lpdeck', 'qml', 'Theme.qml'))
    mine = _tokens(os.path.join(ROOT, 'lpstudio', 'qml', 'Theme.qml'))
    assert deck, 'no tokens parsed from lp-deck'
    assert {k: mine.get(k) for k in deck} == deck


@pytest.fixture(scope='module')
def ui(tmp_path_factory):
    app = QGuiApplication.instance() or QGuiApplication([])
    messages = []
    qInstallMessageHandler(lambda _mode, _ctx, msg: messages.append(msg))
    c = studio.StudioController()
    c.setFamily('smoke')
    settings = tmp_path_factory.mktemp('studio-settings') / 'studio.ini'
    engine = build_engine(c, settings_file=str(settings))
    win = engine.rootObjects()[0]
    win.requestActivate()
    assert QTest.qWaitForWindowActive(win, 2000), 'shortcuts only fire in the active window'
    app.processEvents()
    yield app, win, c, messages
    qInstallMessageHandler(None)
    for item in win.findChildren(MandelPreviewItem):
        item.shutdown()


def _all_items(win):
    root = win.contentItem()
    while root.parentItem() is not None:
        root = root.parentItem()

    def walk(item):
        yield item
        for child in item.childItems():
            yield from walk(child)
    return walk(root)


def _find(win, name):
    for item in _all_items(win):
        if item.objectName() == name:
            return item
    raise LookupError(name)


def _count(win, name):
    return sum(1 for i in _all_items(win) if i.objectName() == name and i.isVisible())


def _call(win, method, *args):
    QMetaObject.invokeMethod(win, method, *(Q_ARG('QVariant', a) for a in args))


def test_the_window_loads_without_qml_warnings(ui):
    _app, _win, _c, messages = ui
    assert [m for m in messages if 'pygame' not in m] == []


def test_the_filter_shows_only_matching_groups(ui):
    app, win, _c, _m = ui
    search = _find(win, 'searchField')
    search.setProperty('text', 'accent')
    app.processEvents()
    try:
        assert _find(win, 'group_Accent ink').isVisible()
        assert _find(win, 'group_Dark accents').isVisible()
        assert not _find(win, 'group_Wisps').isVisible()
        assert not _find(win, 'rampPanel').isVisible()
    finally:
        search.setProperty('text', '')
        app.processEvents()
    assert _find(win, 'group_Wisps').isVisible()


def test_a_group_folds_and_stays_folded(ui):
    app, win, _c, _m = ui
    assert _find(win, 'group_Wisps').property('expanded')
    _call(win, 'setExpanded', 'Wisps', False)
    app.processEvents()
    assert not _find(win, 'group_Wisps').property('expanded')
    _call(win, 'setExpanded', 'Wisps', True)
    app.processEvents()
    assert _find(win, 'group_Wisps').property('expanded')


def test_a_typed_hex_colour_sets_it_and_the_ramp_follows(ui):
    app, win, c, _m = ui
    c.setRampLinked(True)
    field = _find(win, 'hex_smk_light')
    field.forceActiveFocus()
    field.setProperty('text', '#4d7bca')
    QTest.keyClick(win, Qt.Key_Return)
    app.processEvents()
    assert c.colorOf('smk_light') == '#4d7bca'
    assert studio.ramp_colours(c._params)['ink'] == ramp.derive_ramp((77, 123, 202))['ink']
    # Enter lets go of the keyboard, or Ctrl+Z would undo the typing, not the colour
    assert not field.hasActiveFocus()


def test_ctrl_z_undoes_from_the_keyboard(ui):
    app, win, c, _m = ui
    assert win.activeFocusItem() is None or win.activeFocusItem().objectName() != 'hex_smk_light'
    before = c.param('smk_amount')
    c.setParam('smk_amount', 0.55)
    app.processEvents()
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    app.processEvents()
    assert c.param('smk_amount') == pytest.approx(before)
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
    app.processEvents()
    assert c.param('smk_amount') == pytest.approx(0.55)


def test_each_guardrail_gets_a_chip(ui):
    app, win, c, _m = ui
    c.setRampLinked(False)
    for prefix, rgb in zip(('smk_light', 'smk_mid', 'smk_ink', 'smk_acc_ink'), PURPLE_FIRST):
        c.setColor(prefix, studio._hex(rgb))
    app.processEvents()
    assert len(c.guardrails) >= 3
    assert _count(win, 'guardrailChip') == len(c.guardrails)
    c.setRampLinked(True)
    app.processEvents()
    assert _count(win, 'guardrailChip') == len(c.guardrails)
    assert not any(k in ('mid', 'ink', 'accent_ink') for g in c.guardrails for k in g['keys'])


def test_layers_past_the_layer_count_are_hidden(ui):
    app, win, c, _m = ui
    c.setAdvanced(True)
    c.setParam('smk_layers', 3)
    app.processEvents()
    try:
        assert _find(win, 'group_Layer 3').isVisible()
        assert not _find(win, 'group_Layer 4').isVisible()
    finally:
        c.setAdvanced(False)
        app.processEvents()


def test_the_ship_dialog_refuses_a_built_in_name(ui):
    app, win, c, _m = ui
    c.setName('fresh-marble')
    _call(win, 'openShip')
    app.processEvents()
    dialog = win.findChild(QObject, 'shipDialog')
    try:
        name = _find(win, 'shipName')
        assert name.property('text') == 'fresh-marble'
        assert _find(win, 'shipConfirm').property('enabled')
        name.setProperty('text', 'galaxy')
        app.processEvents()
        assert not _find(win, 'shipConfirm').property('enabled')
        assert 'built-in' in _find(win, 'shipVerdict').property('text')
    finally:
        QMetaObject.invokeMethod(dialog, 'close')
        app.processEvents()


def test_the_compare_strip_lists_the_smoke_catalog(ui):
    _app, win, _c, _m = ui
    names = [entry['name'] for entry in win.property('compareModel')]
    assert {'teal-marble', 'purple-marble', 'cobalt-marble'} <= set(names)
    assert _find(win, 'compareStrip').isVisible()


def test_the_theme_button_cycles_system_dark_light(ui):
    app, win, _c, _m = ui
    seen = []
    for _ in range(3):
        _call(win, 'cycleTheme')
        app.processEvents()
        seen.append((win.property('themeMode'), win.property('color').name()))
    assert seen == [('dark', '#15161b'), ('light', '#f5f5f7'), ('system', seen[2][1])]
