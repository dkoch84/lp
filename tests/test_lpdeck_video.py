"""Tests for lp-deck's Video… button: Controller.exportAlbumVideo.

The render itself is lp.video's job (tests/test_video.py). What the deck owns
is the hand-off: the album's own vinyl look (album > artist > global override)
goes on the command line, the subprocess runs off the GUI thread, and its
progress and outcome reach the user as notices. The subprocess is a stub that
prints what lp.video prints.

    .venv/bin/python -m pytest tests/test_lpdeck_video.py
"""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip('PySide6', reason='lp-deck needs PySide6 (requirements-deck.txt)')

from lpdeck import db, qmlapp
from test_lpdeck_features import _controller, _settings
from test_smart_playlists import make_library


@pytest.fixture
def c(tmp_path):
    _settings(tmp_path)
    return _controller(make_library(tmp_path))


class _Proc:
    """A finished lp.video: a few progress lines, then an exit code."""

    def __init__(self, lines, code=0):
        self.stdout = iter(lines)
        self.code = code

    def wait(self):
        return self.code


def _run(c, monkeypatch, lines, code=0, ffmpeg=True):
    """Call exportAlbumVideo with the subprocess stubbed; returns (cmd, notices)."""
    from PySide6.QtCore import QCoreApplication
    started = {}
    done = threading.Event()

    def popen(cmd, **kw):
        started['cmd'] = cmd
        return _Proc(lines, code)

    monkeypatch.setattr(qmlapp.subprocess, 'Popen', popen)
    monkeypatch.setattr(qmlapp.shutil, 'which', lambda name: '/usr/bin/ffmpeg' if ffmpeg else None)
    notices = []
    c.noticeChanged.connect(lambda: notices.append(c.notice))
    real_worker = c._run_video_export

    def worker(*args):
        real_worker(*args)
        done.set()
    monkeypatch.setattr(c, '_run_video_export', worker)

    album_id = c.con.execute("SELECT id FROM albums WHERE name='Heartless'").fetchone()['id']
    ok = c.exportAlbumVideo(album_id, 'file:///tmp/out/Heartless.mp4')
    if ok:
        assert done.wait(5)
    for _ in range(3):
        QCoreApplication.processEvents()      # queued notices from the worker thread
    return ok, started.get('cmd'), notices


def test_the_albums_own_vinyl_look_goes_on_the_command_line(c, monkeypatch):
    album_id = c.con.execute("SELECT id FROM albums WHERE name='Heartless'").fetchone()['id']
    db.set_vinyl_override(c.con, 'album', album_id,
                          {'style': 'nebula-teal-marble', 'label': 'art', 'label_text': 'blocky',
                           'effects': ['glass', 'rim-light'], 'grooves': 'shine'})
    ok, cmd, notices = _run(c, monkeypatch, ['  wrote /tmp/out/Heartless.mp4'])
    assert ok
    assert cmd[1:3] == ['-m', 'lp.video']
    assert cmd[3] == '/music/1/Heartless'
    assert cmd[4] == '/tmp/out/Heartless.mp4'
    assert cmd[cmd.index('--style') + 1] == 'nebula-teal-marble'
    assert cmd[cmd.index('--label-text') + 1] == 'blocky'
    assert cmd[cmd.index('--effects') + 1] == 'glass,rim-light'
    assert cmd[cmd.index('--grooves') + 1] == 'shine'
    assert notices[0].startswith('Rendering “Pallbearer - Heartless”')
    assert notices[-1].startswith('Saved “Pallbearer - Heartless” to Heartless.mp4')


def test_progress_lines_become_notices_and_a_failure_is_reported(c, monkeypatch):
    lines = ['  decoding 1 tracks to one gapless stream...',
             '  Pallbearer - Heartless (2017): 45:00, 81000 frames at 1920x1080@30 (hevc)',
             '  10:00 / 45:00  44 fps, about 13:00 to go',
             'RuntimeError: ffmpeg exited 1']
    ok, cmd, notices = _run(c, monkeypatch, lines, code=1)
    assert ok
    assert any('about 13:00 to go' in n for n in notices)
    assert notices[-1] == 'Video render failed: RuntimeError: ffmpeg exited 1'


def test_without_ffmpeg_nothing_starts(c, monkeypatch):
    ok, cmd, notices = _run(c, monkeypatch, [], ffmpeg=False)
    assert not ok
    assert cmd is None
    assert notices == ["Can't render a video: ffmpeg is not installed."]


def test_a_missing_extension_is_added(c, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    monkeypatch.setattr(qmlapp.shutil, 'which', lambda name: '/usr/bin/ffmpeg')
    seen = {}
    monkeypatch.setattr(c, '_run_video_export', lambda cmd, name, out: seen.update(out=out))
    album_id = c.con.execute("SELECT id FROM albums WHERE name='Heartless'").fetchone()['id']
    assert c.exportAlbumVideo(album_id, 'file:///tmp/out/Heartless')
    for _ in range(3):
        QCoreApplication.processEvents()
    assert seen['out'] == '/tmp/out/Heartless.mp4'
    assert not c.exportAlbumVideo(9999, 'file:///tmp/x.mp4'), 'unknown album'
