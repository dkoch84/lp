"""Tests for lp-deck's transport extras in the controller and MPRIS.

A track that can't be played is skipped and named in a notice; the desktop's
media controls (MPRIS) can seek, set the position, change repeat and shuffle,
and bring the window forward, with changes routed through the controller so the
window stays in step.

    .venv/bin/python -m pytest tests/test_lpdeck_transport.py
"""
import os
import sys

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpdeck import mpris


# --- MPRIS helpers (no D-Bus needed) ----------------------------------------------------

@pytest.mark.parametrize('repeat,status', [('off', 'None'), ('all', 'Playlist'), ('one', 'Track')])
def test_loop_status_round_trips(repeat, status):
    assert mpris.loop_status_for(repeat) == status
    assert mpris.repeat_for_loop_status(status) == repeat


def test_unknown_loop_status_is_ignored():
    assert mpris.repeat_for_loop_status('Sideways') is None
    assert mpris.loop_status_for('nonsense') == 'None'


def test_seek_within_the_track():
    assert mpris.seek_target(30.0, 15_000_000, 200.0) == ('seek', 45.0)
    assert mpris.seek_target(10.0, -60_000_000, 200.0) == ('seek', 0.0)


def test_seek_past_the_end_moves_to_the_next_track():
    assert mpris.seek_target(190.0, 20_000_000, 200.0) == ('next', None)


def test_set_position_outside_the_track_is_ignored():
    assert mpris.set_position_target(12_500_000, 200.0) == 12.5
    assert mpris.set_position_target(-1, 200.0) is None
    assert mpris.set_position_target(250_000_000, 200.0) is None


# --- controller -----------------------------------------------------------------------------

pytest.importorskip('PySide6', reason='lp-deck needs PySide6 (requirements-deck.txt)')


@pytest.fixture
def controller(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QGuiApplication
    from lpdeck import db, qmlapp
    from lpdeck.shot import _FakeBackend, _FakePlayer

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / 'settings'))
    app = QGuiApplication.instance() or QGuiApplication([])
    app.setOrganizationName('lp-deck-test')
    app.setApplicationName('lp-deck-test')
    con = db.connect(str(tmp_path / 'library.db'))
    player = _FakePlayer(_FakeBackend(con))
    player.set_stop_after_current = lambda on: setattr(player, 'stop_after_current', on)
    c = qmlapp.Controller(con, player, qmlapp.ArtistsModel(con), qmlapp.QueueModel(player))
    yield app, c, player
    con.close()


def test_an_unplayable_track_is_named_in_a_notice(controller):
    app, c, player = controller
    player.queue = [{'path': '/music/A/1.flac', 'title': 'Missing Song'}]
    player.backend.last_error = (0, '/music/A/1.flac')
    c._on_backend_event('track_error')
    assert 'Missing Song' in c.notice and "couldn't be played" in c.notice
    c.clearNotice()
    assert c.notice == ''


def test_notice_falls_back_to_the_file_name(controller):
    app, c, player = controller
    player.queue = []
    player.backend.last_error = (3, '/music/A/04 gone.flac')
    c._on_backend_event('track_error')
    assert '04 gone.flac' in c.notice


def test_desktop_requests_update_repeat_shuffle_and_raise(controller):
    app, c, player = controller
    raised = []
    c.raiseRequested.connect(lambda: raised.append(True))
    c._on_external_command('repeat', 'one')
    assert player.repeat == 'one' and c.repeatMode == 'one'
    c._on_external_command('raise', '')
    assert raised == [True]


def test_stop_after_current_toggles(controller):
    app, c, player = controller
    assert c.stopAfterCurrent is False
    c.toggleStopAfterCurrent()
    assert c.stopAfterCurrent is True
    c.toggleStopAfterCurrent()
    assert c.stopAfterCurrent is False
