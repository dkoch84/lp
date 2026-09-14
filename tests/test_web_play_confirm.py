"""Browser tests for the play confirmation and the queue in the kiosk web UI.

With a record on, tapping another album must not cut it off: a sheet asks
first. This is event plumbing in a real browser (a resolved promise gating the
POST, a backdrop tap that must cancel, a footer button that opens the queue),
so it is driven by one, like tests/test_web_track_picker.py, whose harness this
copies. Skips without playwright and a browser.

    .venv/bin/python -m pytest tests/test_web_play_confirm.py
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

TRACKS = ["01 Forgotten Days.flac", "02 Stasis.flac"]


class _Album:
    def __init__(self, name, year):
        self.artist = "Pallbearer"
        self.folder_name = self.display_name = self.name = name
        self.path = f"/music/Pallbearer/{name}"
        self.year = year
        self.cover_path = None
        self.has_cover = False
        self.track_count = len(TRACKS)


ALBUMS = [_Album("Forgotten Days", "2020"), _Album("Heartless", "2017")]


class _Artist:
    name = "Pallbearer"
    albums = ALBUMS


class _Library:
    albums_by_path = {}

    def get_artists(self):
        return [_Artist()]

    def get_artist(self, name):
        return _Artist() if name == "Pallbearer" else None

    def get_album_by_path(self, path):
        return next((a for a in ALBUMS if a.path == path), None)

    def get_album_tracks(self, path):
        return list(TRACKS)


class _Player:
    """A player whose 'playing' state the tests set directly."""

    def __init__(self):
        self.calls = []
        self.current = None
        self.callbacks = {}

    def on(self, event, cb):
        self.callbacks.setdefault(event, []).append(cb)

    def play_album(self, album_path, start=0):
        self.calls.append((album_path, start))
        self.current = next(a for a in ALBUMS if a.path == album_path)

    def stop(self):
        self.current = None
        for cb in self.callbacks.get('stop', []):
            cb()

    def get_status(self):
        if not self.current:
            return {"playing": False, "artist": None, "album": None, "track_title": None,
                    "track_number": 0, "total_tracks": 0, "date": None, "progress": {}}
        return {"playing": True, "artist": "Pallbearer", "album": self.current.name,
                "track_title": "Stasis", "track_number": 2, "total_tracks": 2,
                "date": self.current.year, "progress": {}}


def _free_port():
    with contextlib.closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def ui(chromium):
    import uvicorn

    player = _Player()
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(player, _Library(), static_dir),
                                           host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.skip("test server did not start")

    ctx = chromium.new_context(viewport={"width": 420, "height": 860},
                               is_mobile=True, has_touch=True, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".artist-tile", timeout=15000)
    page.locator(".artist-tile").first.click()
    page.wait_for_selector(".album-tile", timeout=15000)

    class _UI:
        def __init__(self):
            self.page, self.player = page, player

        def tile(self, name):
            return page.locator("#album-grid .album-tile", has_text=name).first

        def tap_cover(self, name):
            self.tile(name).locator(".album-cover, .album-cover-placeholder").first.tap()
            page.wait_for_timeout(400)

        def sheet_open(self):
            return page.locator("#play-sheet:not(.hidden)").count() > 0

        def queue_open(self):
            return page.locator("#queue-sheet:not(.hidden)").count() > 0

        def sync_status(self):
            """The UI polls every 3 s; force a poll so lastStatus is current."""
            page.evaluate("pollStatus()")
            page.wait_for_timeout(300)

    yield _UI()
    ctx.close()
    server.should_exit = True


@pytest.fixture(autouse=True)
def _reset(ui):
    ui.player.calls.clear()
    ui.player.current = None
    ui.page.evaluate("fetch('/api/queue/clear', {method: 'POST'})")
    ui.page.keyboard.press("Escape")
    ui.sync_status()
    yield


def test_nothing_playing_a_tap_just_plays(ui):
    ui.tap_cover("Heartless")
    assert not ui.sheet_open()
    assert ui.player.calls == [(ALBUMS[1].path, 0)]


def test_with_a_record_on_a_tap_asks_first(ui):
    ui.player.current = ALBUMS[0]
    ui.sync_status()
    ui.tap_cover("Heartless")
    assert ui.sheet_open()
    assert ui.player.calls == [], "nothing was cut off"
    title = ui.page.locator("#play-sheet-title").inner_text()
    assert "Forgotten Days" in title and "Heartless" in title


def test_play_now_cuts_over(ui):
    ui.player.current = ALBUMS[0]
    ui.sync_status()
    ui.tap_cover("Heartless")
    ui.page.locator("#play-sheet-now").tap()
    ui.page.wait_for_timeout(400)
    assert not ui.sheet_open()
    assert ui.player.calls == [(ALBUMS[1].path, 0)]


def test_play_next_queues_and_the_footer_says_so(ui):
    ui.player.current = ALBUMS[0]
    ui.sync_status()
    ui.tap_cover("Heartless")
    ui.page.locator("#play-sheet-next").tap()
    ui.page.wait_for_timeout(500)
    assert ui.player.calls == [], "queued, not played"
    ui.sync_status()
    assert ui.page.locator("#np-queue").inner_text() == "Next: Heartless"

    ui.page.locator("#np-queue").tap()
    ui.page.wait_for_timeout(300)
    assert ui.queue_open()
    assert ui.page.locator("#queue-sheet-list li").count() == 1
    ui.page.locator("#queue-sheet-list .queue-remove").first.tap()
    ui.page.wait_for_timeout(400)
    assert "Nothing queued" in ui.page.locator("#queue-sheet-list").inner_text()


def test_cancel_and_backdrop_leave_the_record_alone(ui):
    ui.player.current = ALBUMS[0]
    ui.sync_status()
    ui.tap_cover("Heartless")
    ui.page.locator("#play-sheet-cancel").tap()
    ui.page.wait_for_timeout(200)
    assert not ui.sheet_open()
    ui.tap_cover("Heartless")
    ui.page.locator("#play-sheet-backdrop").tap(position={"x": 10, "y": 10})
    ui.page.wait_for_timeout(200)
    assert not ui.sheet_open()
    assert ui.player.calls == []
