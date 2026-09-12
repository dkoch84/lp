"""Browser tests for the kiosk web UI's track picker.

Tapping an album cover plays it from the top. Tapping the caption strip beneath
it opens the picker, to start from a chosen track.

WHY A BROWSER TEST
------------------
This control was a long press first, and it shipped broken twice. Both faults
lived entirely in the browser and neither was reachable from a unit test: on
Chrome/Android the native long-press won the race, showed "copy image / save
image" and fired pointercancel, and once that was worked around, the click
synthesised on release closed the sheet the instant it opened. Headless touch
emulation did not reproduce the first one either, which is how the second fix
got shipped still broken.

The lesson kept here is not the long press, which is gone: it is that anything
in this UI that depends on how a real browser dispatches events has to be driven
by a real browser. Two things this file pins down as a result:

  * tapping the cover and tapping the caption do genuinely different things,
    which is entirely a question of event targets and propagation;
  * the ordinary tap-to-play path is untouched, since the picker is an escape
    hatch and must not cost anything in normal use.

Requirements: `pip install -r requirements-dev.txt`, plus a browser. The system
Google Chrome is used when present; otherwise run `python -m playwright install
chromium` once. Without either the module skips rather than fails, so the suite
still runs on the kiosk. See the `chromium` fixture in conftest.py.

    .venv/bin/python -m pytest tests/test_web_track_picker.py
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

ALBUM_PATH = "/music/Pallbearer/Forgotten Days"
TRACKS = ["01 Forgotten Days.flac", "02 Stasis.flac", "03 Rite of Ruin.flac",
          "04 Silver Wings.flac", "05 Caledonia.flac"]


class _Album:
    artist = "Pallbearer"
    folder_name = "Forgotten Days"
    display_name = "Forgotten Days"
    name = "Forgotten Days"
    path = ALBUM_PATH
    year = "2020"
    cover_path = None
    has_cover = False
    track_count = len(TRACKS)


class _Artist:
    name = "Pallbearer"
    albums = [_Album()]


class _Library:
    albums_by_path = {}

    def get_artists(self):
        return [_Artist()]

    def get_artist(self, name):
        return _Artist() if name == "Pallbearer" else None

    def get_album_by_path(self, path):
        return _Album() if path == ALBUM_PATH else None

    def get_album_tracks(self, path):
        return list(TRACKS)


class _Player:
    """Records what the UI asked to play."""

    def __init__(self):
        self.calls = []

    def play_album(self, album_path, start=0):
        self.calls.append((album_path, start))

    def stop(self):
        pass

    def get_status(self):
        return {"playing": False, "artist": None, "album": None,
                "track_title": None, "track_number": 0, "total_tracks": 0,
                "date": None, "progress": {}}


def _free_port():
    with contextlib.closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def ui(chromium):
    """The real app in a real browser, sitting on the album grid."""
    import uvicorn

    player = _Player()
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(player, _Library(), static_dir),
        host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.skip("test server did not start")

    ctx = chromium.new_context(viewport={"width": 420, "height": 860},
                               is_mobile=True, has_touch=True,
                               device_scale_factor=2)
    page = ctx.new_page()
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".artist-tile", timeout=15000)
    page.locator(".artist-tile").first.click()
    page.wait_for_selector(".album-tile", timeout=15000)

    class _UI:
        def __init__(self):
            self.page = page
            self.player = player
            self.tile = page.locator(".album-tile").first

        def tap_cover(self):
            self.tile.locator(".album-cover, .album-cover-placeholder").first.tap()
            page.wait_for_timeout(400)

        def tap_caption(self):
            self.tile.locator(".album-caption").tap()
            page.wait_for_timeout(500)

        def sheet_open(self):
            return page.locator("#track-sheet:not(.hidden)").count() > 0

        def rows(self):
            return page.locator("#track-sheet-list li")

        def close_sheet(self):
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)

    yield _UI()
    ctx.close()
    server.should_exit = True


@pytest.fixture(autouse=True)
def _reset(ui):
    ui.player.calls.clear()
    if ui.sheet_open():
        ui.close_sheet()
    yield


# --- the ordinary path must be untouched -----------------------------------

def test_tapping_the_cover_plays_from_the_top(ui):
    ui.tap_cover()
    assert ui.player.calls == [(ALBUM_PATH, 0)]


def test_tapping_the_cover_does_not_open_the_picker(ui):
    ui.tap_cover()
    assert not ui.sheet_open()


# --- the picker ------------------------------------------------------------

def test_tapping_the_caption_opens_the_picker(ui):
    ui.tap_caption()
    assert ui.sheet_open()


def test_tapping_the_caption_does_not_start_playback(ui):
    """The caption sits inside the tile, whose own click plays the album. If
    propagation ever stops being stopped, opening the picker would also start
    the record from the top."""
    ui.tap_caption()
    assert ui.player.calls == []


def test_picker_lists_every_track(ui):
    ui.tap_caption()
    assert ui.rows().count() == len(TRACKS)


def test_rows_show_filenames_with_the_extension_trimmed(ui):
    ui.tap_caption()
    assert ui.rows().nth(2).inner_text().strip().endswith("03 Rite of Ruin")


def test_choosing_a_row_plays_from_that_index(ui):
    ui.tap_caption()
    ui.rows().nth(2).click()
    ui.page.wait_for_timeout(400)
    assert ui.player.calls == [(ALBUM_PATH, 2)]


def test_choosing_the_last_row_plays_the_last_track(ui):
    """Finishing an album from its final track, which is what this is for."""
    ui.tap_caption()
    ui.rows().nth(len(TRACKS) - 1).click()
    ui.page.wait_for_timeout(400)
    assert ui.player.calls == [(ALBUM_PATH, len(TRACKS) - 1)]


def test_choosing_a_row_closes_the_picker(ui):
    ui.tap_caption()
    ui.rows().nth(0).click()
    ui.page.wait_for_timeout(400)
    assert not ui.sheet_open()


def test_backdrop_dismisses_without_playing(ui):
    ui.tap_caption()
    ui.page.locator("#track-sheet-backdrop").click()
    ui.page.wait_for_timeout(300)
    assert not ui.sheet_open()
    assert ui.player.calls == []
