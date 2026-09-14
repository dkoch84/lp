"""Browser tests for the release pill and its sheet in the kiosk web UI.

Tapping the release name in the header opens a sheet with what is installed,
the release notes link and, on a managed install, the update controls. A git
checkout gets the sheet without the controls. Driven in a real browser like
the other test_web_* files; skips without playwright and a browser.

    .venv/bin/python -m pytest tests/test_web_release_sheet.py
"""
import contextlib
import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright not installed (requirements-dev.txt)")

from lp.api import create_app


class _Library:
    albums_by_path = {}

    def get_artists(self):
        return []


class _Player:
    def on(self, *_):
        pass

    def get_status(self):
        return {"playing": False, "artist": None, "album": None, "track_title": None,
                "track_number": 0, "total_tracks": 0, "date": None, "progress": {}}


class _Updates:
    """A managed install with a newer release out; records what the UI asks."""

    def __init__(self, managed=True):
        self.managed = managed
        self.calls = []
        self.pending = None

    def status(self):
        return {"managed": self.managed, "auto": True, "current": "crucible",
                "current_title": "Crucible",
                "latest": "ruin", "latest_title": "Ruin", "available": "ruin",
                "url": "https://github.com/dkoch84/lp/releases/tag/ruin",
                "checked_at": time.time(), "state": "idle", "error": None,
                "pending": self.pending, "installed": None, "progress": {}}

    def check(self):
        self.calls.append("check")
        return self.status()

    def install(self, when):
        self.calls.append(("install", when))
        self.pending = None if when == "cancel" else when
        return self.status()


def _free_port():
    with contextlib.closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(updates):
    import uvicorn
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(_Player(), _Library(), static_dir, updates=updates),
        host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.skip("test server did not start")
    return server, port


@pytest.fixture(scope="module")
def managed(chromium):
    updates = _Updates()
    server, port = _serve(updates)
    ctx = chromium.new_context(viewport={"width": 420, "height": 860}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_timeout(300)
    yield page, updates
    ctx.close()
    server.should_exit = True


@pytest.fixture(scope="module")
def checkout(chromium):
    server, port = _serve(None)
    ctx = chromium.new_context(viewport={"width": 420, "height": 860}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_timeout(300)
    yield page
    ctx.close()
    server.should_exit = True


def _open(page):
    page.locator("#brand").tap()
    page.wait_for_timeout(300)
    return page.locator("#release-sheet:not(.hidden)")


def test_the_pill_opens_the_sheet_and_shows_the_newer_release(managed):
    page, updates = managed
    assert page.locator("#brand-release.update").count() == 1, "a dot marks the update"
    assert _open(page).count() == 1
    status = page.locator("#release-sheet-status").inner_text()
    assert "Ruin is out" in status and "Crucible" in status
    assert page.locator("#release-sheet-notes").get_attribute("href").endswith("/tag/ruin")
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    assert page.locator("#release-sheet:not(.hidden)").count() == 0


def test_install_after_this_album_is_one_tap(managed):
    page, updates = managed
    _open(page)
    page.locator("#update-idle").tap()
    page.wait_for_timeout(300)
    assert ("install", "idle") in updates.calls
    assert page.locator("#update-cancel:not(.hidden)").count() == 1
    page.locator("#update-cancel").tap()
    page.wait_for_timeout(300)
    assert ("install", "cancel") in updates.calls
    page.locator("#release-sheet-close").tap()


def test_a_checkout_gets_the_sheet_without_controls(checkout):
    page = checkout
    assert page.locator("#brand-release.update").count() == 0
    assert _open(page).count() == 1
    assert "git" in page.locator("#release-sheet-status").inner_text()
    for control in ("#update-check", "#update-now", "#update-idle", "#update-cancel"):
        assert page.locator(f"{control}:not(.hidden)").count() == 0
    assert page.locator("#release-sheet-notes").is_visible()
