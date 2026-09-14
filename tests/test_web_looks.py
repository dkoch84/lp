"""Browser tests for the vinyl page's scope bar: All albums vs This album.

The bar decides where an edit goes, and it is JavaScript state layered on
every settings POST, so it is driven in a real browser like the other
test_web_* files. Skips without playwright and a browser.

    .venv/bin/python -m pytest tests/test_web_looks.py
"""
import contextlib
import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright not installed (requirements-dev.txt)")

from lp.api import create_app
from lp.looks import Looks
from lpcore.vinyl.settings import VinylSettings
from test_looks import _Player
from test_queue import ALBUMS, _Library


def _free_port():
    with contextlib.closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def rig(chromium, tmp_path_factory):
    import uvicorn
    settings = VinylSettings()
    player = _Player()
    looks = Looks(str(tmp_path_factory.mktemp("looks") / "looks.json"), settings, player)
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(player, _Library(), static_dir, settings=settings, looks=looks),
        host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.skip("test server did not start")
    ctx = chromium.new_context(viewport={"width": 420, "height": 860}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    yield page, settings, player, looks, f"http://127.0.0.1:{port}/vinyl.html"
    ctx.close()
    server.should_exit = True


def _open(page, url):
    page.goto(url, wait_until="networkidle")
    page.wait_for_selector("#scope-album", timeout=15000)
    page.wait_for_timeout(300)


def _wait(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def test_with_nothing_playing_only_all_albums_is_offered(rig):
    page, settings, player, looks, url = rig
    player.stop()
    _open(page, url)
    assert page.locator("#scope-album").is_disabled()
    assert page.locator("#scope-album").inner_text() == "Nothing playing"
    page.locator("#controls-root input[type=range]").first.fill("40")
    page.locator("#controls-root input[type=range]").first.dispatch_event("change")
    assert _wait(lambda: settings.brightness == 40)
    assert looks.global_look.get("brightness") == 40


def test_this_album_scope_keeps_the_look_for_the_playing_album(rig):
    page, settings, player, looks, url = rig
    player.play(ALBUMS[1].path)
    _open(page, url)
    assert page.locator("#scope-album").inner_text() == "This album: Pallbearer - Heartless"
    page.locator("#scope-album").tap()
    assert "starts a look" in page.locator("#scope-note").inner_text()
    page.locator(".effect-row input[value='glass']").check()
    assert _wait(lambda: settings.effects == ["glass"])
    assert ALBUMS[1].path in looks.album_looks
    assert "glass" not in (looks.global_look.get("effects") or [])
    assert _wait(lambda: "keeps its own look" in page.locator("#scope-note").inner_text())

    # Reopening the page lands on the album scope, since that is what shows.
    _open(page, url)
    assert page.locator("#scope-album").evaluate("el => el.classList.contains('active')")
    page.locator("#scope-note button", has_text="Forget it").tap()
    assert _wait(lambda: ALBUMS[1].path not in looks.album_looks)
    assert settings.effects == []


def test_the_background_section_posts_colors(rig):
    page, settings, player, looks, url = rig
    player.stop()
    _open(page, url)
    page.locator("#controls-root button", has_text="Both pure black").tap()
    assert _wait(lambda: settings.panel_color == "#000000" and settings.frame_color == "#000000")
    assert looks.global_look["panel_color"] == "#000000"
