"""Browser tests for the web UI's history handling.

The UI is one page. Without history entries the back button leaves the site
instead of going up a level, which is the complaint this answers. A router is
easy to get half-right in ways only a real browser shows: an entry pushed twice,
a dialog that reopens when you go back past it, a pasted link with nothing
behind it, a forward button that does nothing.

Every assertion below is therefore about real navigation: page.go_back(),
page.go_forward(), page.reload(), and the address bar.

Requirements: `pip install -r requirements-dev.txt`, plus a browser. The system
Google Chrome is used when present; otherwise run `python -m playwright install
chromium` once. Without either the module skips rather than fails, so the suite
still runs on the kiosk. See the `chromium` fixture in conftest.py.

    .venv/bin/python -m pytest tests/test_web_routing.py
"""
import contextlib
import os
import socket
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright not installed (requirements-dev.txt)")

from lp.api import create_app

ARTISTS = ["Pallbearer", "Sunn O)))"]
ALBUM_PATHS = {
    ("Pallbearer", "Forgotten Days"): "/music/Pallbearer/Forgotten Days",
    ("Pallbearer", "Heartless"): "/music/Pallbearer/Heartless",
    ("Sunn O)))", "Monoliths"): "/music/Sunn O)))/Monoliths",
}
TRACKS = ["1 One.flac", "2 Two.flac", "10 Ten.flac"]


class _Album:
    def __init__(self, artist, name):
        self.artist = artist
        self.name = name
        self.display_name = name
        self.folder_name = name
        self.path = ALBUM_PATHS[(artist, name)]
        self.year = "2020"
        self.cover_path = None
        self.track_count = len(TRACKS)


class _Artist:
    def __init__(self, name):
        self.name = name
        self.albums = [_Album(a, n) for (a, n) in ALBUM_PATHS if a == name]


class _Library:
    albums_by_path = {}

    def get_artists(self):
        return [_Artist(n) for n in ARTISTS]

    def get_artist(self, name):
        return _Artist(name) if name in ARTISTS else None

    def get_album_by_path(self, path):
        for (artist, name), p in ALBUM_PATHS.items():
            if p == path:
                return _Album(artist, name)
        return None

    def get_album_tracks(self, path):
        return list(TRACKS)


# Smallest valid PNG: 1x1, fully transparent.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082")


class _Display:
    def request_screenshot(self, timeout=8.0):
        return _PNG


class _Player:
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
def browser_ctx(chromium):
    import uvicorn

    player = _Player()
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(player, _Library(), static_dir, display=_Display()),
        host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.skip("test server did not start")

    yield chromium, f"http://127.0.0.1:{port}", player
    server.should_exit = True


@pytest.fixture
def page(browser_ctx):
    """A fresh context per test: history is what is under test, so it must not
    leak between them."""
    browser, base, player = browser_ctx
    player.calls.clear()
    ctx = browser.new_context(viewport={"width": 420, "height": 860},
                              is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.on("dialog", lambda d: d.dismiss())   # an alert() would hang the run
    pg.base = base
    pg.player = player
    yield pg
    ctx.close()


# --- helpers ---------------------------------------------------------------

def _query(page):
    return {k: v[0] for k, v in parse_qs(urlparse(page.url).query).items()}


def _open(page, path="/"):
    page.goto(page.base + path, wait_until="networkidle")
    page.wait_for_timeout(300)


def _artists_visible(page):
    return page.locator("#artist-grid:not(.hidden)").count() > 0


def _albums_visible(page):
    return page.locator("#album-grid:not(.hidden)").count() > 0


def _sheet_open(page):
    return page.locator("#track-sheet:not(.hidden)").count() > 0


def _open_artist(page, name="Pallbearer"):
    page.locator(".artist-tile", has_text=name).first.click()
    page.wait_for_timeout(400)


def _open_picker(page):
    page.locator(".album-tile .album-caption").first.click()
    page.wait_for_timeout(500)


# --- the URL describes the view --------------------------------------------

def test_artist_grid_is_the_bare_url(page):
    _open(page)
    assert _artists_visible(page)
    assert _query(page) == {}


def test_opening_an_artist_puts_it_in_the_url(page):
    _open(page)
    _open_artist(page)
    assert _albums_visible(page)
    assert _query(page) == {"artist": "Pallbearer"}


def test_opening_the_picker_puts_the_album_in_the_url(page):
    _open(page)
    _open_artist(page)
    _open_picker(page)
    assert _sheet_open(page)
    assert _query(page)["artist"] == "Pallbearer"
    assert "tracks" in _query(page)


# --- back and forward ------------------------------------------------------

def test_back_from_an_artist_returns_to_the_grid(page):
    """The complaint: this used to leave the site."""
    _open(page)
    _open_artist(page)
    page.go_back()
    page.wait_for_timeout(400)
    assert _artists_visible(page)
    assert _query(page) == {}


def test_forward_returns_to_the_artist(page):
    _open(page)
    _open_artist(page)
    page.go_back()
    page.wait_for_timeout(400)
    page.go_forward()
    page.wait_for_timeout(400)
    assert _albums_visible(page)
    assert _query(page) == {"artist": "Pallbearer"}


def test_back_closes_the_picker_and_stays_on_the_albums(page):
    _open(page)
    _open_artist(page)
    _open_picker(page)
    page.go_back()
    page.wait_for_timeout(400)
    assert not _sheet_open(page)
    assert _albums_visible(page)
    assert _query(page) == {"artist": "Pallbearer"}


def test_back_twice_from_the_picker_reaches_the_grid(page):
    _open(page)
    _open_artist(page)
    _open_picker(page)
    page.go_back()
    page.wait_for_timeout(300)
    page.go_back()
    page.wait_for_timeout(400)
    assert _artists_visible(page)
    assert _query(page) == {}


def test_dismissing_the_picker_does_not_leave_it_in_history(page):
    """Closing by backdrop must consume its entry, or back would reopen it."""
    _open(page)
    _open_artist(page)
    _open_picker(page)
    page.locator("#track-sheet-backdrop").click()
    page.wait_for_timeout(400)
    assert not _sheet_open(page)

    page.go_back()
    page.wait_for_timeout(400)
    assert not _sheet_open(page), "back reopened the picker"
    assert _artists_visible(page)


def test_choosing_a_track_does_not_leave_the_picker_in_history(page):
    _open(page)
    _open_artist(page)
    _open_picker(page)
    page.locator("#track-sheet-list li").nth(1).click()
    page.wait_for_timeout(500)
    assert page.player.calls == [(ALBUM_PATHS[("Pallbearer", "Forgotten Days")], 1)]

    page.go_back()
    page.wait_for_timeout(400)
    assert not _sheet_open(page), "back reopened the picker after choosing"


def test_header_back_button_and_browser_back_agree(page):
    _open(page)
    _open_artist(page)
    page.locator("#back-btn").click()
    page.wait_for_timeout(400)
    assert _artists_visible(page)
    assert _query(page) == {}


# --- deep links ------------------------------------------------------------

def test_a_pasted_artist_link_opens_that_artist(page):
    _open(page, "/?artist=Pallbearer")
    assert _albums_visible(page)
    assert page.locator("#header-title").inner_text().strip() == "Pallbearer"


def test_back_from_a_pasted_artist_link_reaches_the_grid_not_the_void(page):
    """A pasted link has nothing behind it unless the router seeds it."""
    _open(page, "/?artist=Pallbearer")
    page.go_back()
    page.wait_for_timeout(500)
    assert _artists_visible(page), "back left the app"
    assert _query(page) == {}


def test_header_back_on_a_pasted_link_reaches_the_grid(page):
    _open(page, "/?artist=Pallbearer")
    page.locator("#back-btn").click()
    page.wait_for_timeout(500)
    assert _artists_visible(page)


def test_a_pasted_picker_link_opens_the_picker_over_the_albums(page):
    _open(page, "/?artist=Pallbearer&tracks=Forgotten+Days")
    assert _sheet_open(page)
    assert page.locator("#track-sheet-list li").count() == len(TRACKS)


def test_back_from_a_pasted_picker_link_walks_down_the_levels(page):
    _open(page, "/?artist=Pallbearer&tracks=Forgotten+Days")
    page.go_back()
    page.wait_for_timeout(400)
    assert not _sheet_open(page)
    assert _albums_visible(page)

    page.go_back()
    page.wait_for_timeout(400)
    assert _artists_visible(page)


def test_an_unknown_artist_falls_back_to_the_grid(page):
    _open(page, "/?artist=Nobody+At+All")
    assert _artists_visible(page)
    assert _query(page) == {}


# --- reload ----------------------------------------------------------------

def test_reload_keeps_you_on_the_artist(page):
    _open(page)
    _open_artist(page)
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(400)
    assert _albums_visible(page)
    assert _query(page) == {"artist": "Pallbearer"}


def test_history_does_not_grow_an_entry_per_render(page):
    """A router that pushes on every apply makes back need N presses."""
    _open(page)
    _open_artist(page)
    _open_picker(page)
    page.go_back()
    page.wait_for_timeout(300)
    page.go_back()
    page.wait_for_timeout(400)
    assert _artists_visible(page), "took more than two backs to reach the grid"


# --- the share modal is history-aware without being in the URL -------------

def _share_open(page):
    return page.locator("#share-modal:not(.hidden)").count() > 0


def _open_share(page):
    page.locator("#share-btn").click()
    page.wait_for_selector("#share-modal:not(.hidden)", timeout=10000)


def test_share_modal_opens(page):
    _open(page)
    _open_share(page)
    assert _share_open(page)


def test_share_modal_does_not_touch_the_url(page):
    """A URL saying "share" would take a fresh screenshot on every reload."""
    _open(page)
    _open_artist(page)
    before = page.url
    _open_share(page)
    assert page.url == before


def test_back_closes_the_share_modal(page):
    """The ask: back should dismiss it, not navigate the page underneath."""
    _open(page)
    _open_artist(page)
    _open_share(page)
    page.go_back()
    page.wait_for_timeout(400)
    assert not _share_open(page)
    assert _albums_visible(page), "back navigated instead of closing the modal"
    assert _query(page) == {"artist": "Pallbearer"}


def test_closing_the_share_modal_does_not_leave_it_in_history(page):
    _open(page)
    _open_artist(page)
    _open_share(page)
    page.locator("#share-modal-close").click()
    page.wait_for_timeout(400)
    assert not _share_open(page)

    page.go_back()
    page.wait_for_timeout(400)
    assert not _share_open(page), "back reopened the share modal"
    assert _artists_visible(page)


def test_backdrop_dismisses_the_share_modal(page):
    _open(page)
    _open_share(page)
    # A corner: the modal content sits over the middle of the backdrop.
    page.locator("#share-modal-backdrop").click(position={"x": 5, "y": 5})
    page.wait_for_timeout(400)
    assert not _share_open(page)
    assert _artists_visible(page)


def test_forward_does_not_reopen_a_revoked_screenshot(page):
    """Closing revokes the blob, so forward has nothing to show and must not
    present an empty modal."""
    _open(page)
    _open_share(page)
    page.go_back()
    page.wait_for_timeout(300)
    page.go_forward()
    page.wait_for_timeout(400)
    assert not _share_open(page)
