"""Tests for keeping the computer awake while playing, and for one lp-deck at a time.

    .venv/bin/python -m pytest tests/test_inhibit_single_instance.py
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpdeck import inhibit
from lpdeck.inhibit import SleepInhibitor


def test_holds_the_lock_only_while_asked():
    inh = SleepInhibitor(command=['sleep', '60'])
    inh.set_active(True)
    proc = inh._proc
    assert inh.active
    inh.set_active(True)
    assert inh._proc is proc                   # still one process
    inh.set_active(False)
    assert not inh.active
    assert proc.poll() is not None


def test_disabled_or_unavailable_does_nothing():
    inh = SleepInhibitor(command=['sleep', '60'])
    inh.enabled = False
    inh.set_active(True)
    assert not inh.active
    none = SleepInhibitor(command=[])
    none.set_active(True)
    assert not none.active


def test_a_missing_program_is_not_an_error():
    inh = SleepInhibitor(command=['/nonexistent/systemd-inhibit'])
    inh.set_active(True)
    assert not inh.active


def test_shutdown_releases_the_lock():
    inh = SleepInhibitor(command=['sleep', '60'])
    inh.set_active(True)
    proc = inh._proc
    inh.shutdown()
    assert proc.poll() is not None
    inh.set_active(True)
    assert not inh.active


def test_default_command_blocks_sleep_and_idle(monkeypatch):
    monkeypatch.setattr(inhibit.shutil, 'which', lambda name: '/usr/bin/' + name)
    cmd = inhibit.default_command()
    assert cmd[0] == '/usr/bin/systemd-inhibit'
    assert '--what=sleep:idle' in cmd and '--mode=block' in cmd
    monkeypatch.setattr(inhibit.shutil, 'which', lambda name: None)
    assert inhibit.default_command() is None


# --- single instance -----------------------------------------------------------------------

@pytest.fixture
def app():
    pytest.importorskip('PySide6', reason='lp-deck needs PySide6 (requirements-deck.txt)')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def _wait_for(app, got):
    deadline = time.monotonic() + 5
    while not got and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def test_a_second_launch_hands_over_its_files(app, tmp_path):
    from lpdeck.single_instance import InstanceServer, send_to_running
    name = f'lp-deck-test-{os.getpid()}'
    server = InstanceServer(name=name)
    assert server.listen()
    got = []
    server.opened.connect(got.append)
    try:
        assert send_to_running(['relative.flac', str(tmp_path / 'folder')], name=name)
        _wait_for(app, got)
    finally:
        server.close()
    assert got == [[os.path.abspath('relative.flac'), str(tmp_path / 'folder')]]


def test_a_bare_second_launch_still_reaches_the_first(app):
    from lpdeck.single_instance import InstanceServer, send_to_running
    name = f'lp-deck-test-bare-{os.getpid()}'
    server = InstanceServer(name=name)
    assert server.listen()
    got = []
    server.opened.connect(got.append)
    try:
        assert send_to_running([], name=name)
        _wait_for(app, got)
    finally:
        server.close()
    assert got == [[]]                         # nothing to open: just come forward


def test_no_running_instance(app):
    from lpdeck.single_instance import send_to_running
    assert not send_to_running(['x.flac'], name=f'lp-deck-test-nobody-{os.getpid()}',
                               timeout_ms=200)
