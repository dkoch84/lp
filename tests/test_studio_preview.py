"""Tests for lp-studio's live preview: renders must not freeze the window.

A layered-smoke render takes seconds. It used to run on the UI thread, which
froze every slider and text box until it finished. Now it runs in a worker
process, so these check the event loop keeps turning during a render, and that
changes made mid-render still end up on screen.

    .venv/bin/python -m pytest tests/test_studio_preview.py
"""
import os
import sys
import time

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip('PySide6', reason='lp-studio needs PySide6 (requirements-deck.txt)')

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QGuiApplication

from lpstudio import studio
from lpstudio.preview_item import MandelPreviewItem, render_job


@pytest.fixture(scope='module')
def app():
    return QGuiApplication.instance() or QGuiApplication([])


def _wait_for_render(app, item, timeout=60.0):
    """Run the event loop until the item shows a render; count loop ticks."""
    ticks = []
    beat = QTimer()
    beat.setInterval(20)
    beat.timeout.connect(lambda: ticks.append(time.monotonic()))
    beat.start()
    loop = QEventLoop()
    item.rendered.connect(loop.quit)
    QTimer.singleShot(int(timeout * 1000), loop.quit)
    loop.exec()
    beat.stop()
    item.rendered.disconnect(loop.quit)
    return ticks


def test_render_job_returns_picklable_frames():
    from lpcore.vinyl import fractals
    try:
        body, grooves, blend, shine = render_job(dict(studio.DEFAULTS), 'smoke', False, 30)
    finally:
        # render_job is meant for the worker process and turns the field cache
        # on; run here it would leave the cache on for every later test.
        fractals.disable_field_cache()
    for w, h, data in (body, grooves, shine):
        assert (w, h) == (60, 60) and len(data) == 60 * 60 * 4
    assert blend in ('add', 'blend')


def test_smoke_render_does_not_block_the_event_loop(app):
    c = studio.StudioController()
    c.setFamily('smoke')
    item = MandelPreviewItem()
    try:
        started = time.monotonic()
        item.setController(c)          # kicks off the first render
        ticks = _wait_for_render(app, item)
        took = time.monotonic() - started
        assert item._disc is not None, 'render never arrived'
        # a blocked loop would tick once or twice; a free one ~50 times a second
        assert len(ticks) > took * 20, f'{len(ticks)} ticks in {took:.1f}s'
    finally:
        item.shutdown()


def test_changes_made_mid_render_are_rendered_next(app):
    c = studio.StudioController()
    c.setFamily('smoke')
    item = MandelPreviewItem()
    try:
        item.setController(c)
        c.setParam('smk_acc_count', 2)     # arrives while the first render runs
        item._render()                     # skip the debounce
        assert item._stale
        _wait_for_render(app, item)        # the first render
        assert item._job is not None, 'the newer settings were not queued'
        _wait_for_render(app, item)        # the one with smk_acc_count=2
        assert item._job is None and not item._stale
    finally:
        item.shutdown()


def test_a_dead_worker_is_replaced(app):
    c = studio.StudioController()
    c.setFamily('smoke')
    item = MandelPreviewItem()
    try:
        item.setController(c)
        _wait_for_render(app, item)
        for proc in list(item._pool._processes.values()):
            proc.kill()
        time.sleep(0.5)
        first = item._disc
        c.setParam('smk_seed', 7)
        item._render()
        _wait_for_render(app, item)
        if item._disc is first:            # the first attempt reported the dead worker
            _wait_for_render(app, item)
        assert item._disc is not first, 'no render after the worker died'
    finally:
        item.shutdown()
