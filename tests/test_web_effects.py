"""Browser test for the kiosk web UI's Vinyl Effects checkboxes.

The vinyl page builds its Effects section from `/api/settings/effects` and
posts the whole chosen set on every change. What can break silently is the
browser half: a checkbox that doesn't reflect the saved state, or a change that
posts the wrong set. So this drives the real page against the real app and
reads the settings object the display renders from.

Requirements as for the other browser tests: see the `chromium` fixture in
conftest.py; without a browser the module skips.

    .venv/bin/python -m pytest tests/test_web_effects.py
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
from lpcore.vinyl.settings import VinylSettings


class _Library:
    albums_by_path = {}

    def get_artists(self):
        return []


class _Player:
    def get_status(self):
        return {"playing": False}


def _free_port():
    with contextlib.closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def kiosk(chromium):
    import uvicorn

    settings = VinylSettings().update(effects=["rim-light"], grooves="shine")
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(_Player(), _Library(), static_dir, settings=settings),
        host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.skip("test server did not start")

    ctx = chromium.new_context(viewport={"width": 420, "height": 860})
    page = ctx.new_page()
    page.goto(f"http://127.0.0.1:{port}/vinyl.html", wait_until="networkidle")
    page.wait_for_selector(".effect-row", timeout=15000)
    yield page, settings
    ctx.close()
    server.should_exit = True


def _box(page, effect_id):
    return page.locator(f'.effect-row input[value="{effect_id}"]')


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_lists_every_effect_by_name(kiosk):
    page, _settings = kiosk
    labels = [t.strip() for t in page.locator(".effect-row").all_inner_texts()]
    assert labels == ["Glass", "Deep edge", "Rim light"]


def test_checkboxes_show_the_saved_effects(kiosk):
    page, _settings = kiosk
    assert _box(page, "rim-light").is_checked()
    assert not _box(page, "glass").is_checked()
    assert not _box(page, "deep-edge").is_checked()


def test_ticking_and_unticking_updates_what_the_display_renders(kiosk):
    page, settings = kiosk
    _box(page, "glass").check()
    assert _wait_for(lambda: settings.effects == ["glass", "rim-light"]), settings.effects
    _box(page, "rim-light").uncheck()
    assert _wait_for(lambda: settings.effects == ["glass"]), settings.effects
    _box(page, "glass").uncheck()
    assert _wait_for(lambda: settings.effects == []), settings.effects



def _radio(page, treatment):
    return page.locator(f'.groove-row input[value="{treatment}"]')


def test_grooves_radios_show_the_saved_treatment(kiosk):
    page, _settings = kiosk
    labels = [t.strip() for t in page.locator(".groove-row").all_inner_texts()]
    assert labels == ["Auto", "Shine", "Shadow", "Smooth"]
    assert _radio(page, "shine").is_checked()


def test_picking_a_groove_treatment_updates_what_the_display_renders(kiosk):
    page, settings = kiosk
    _radio(page, "smooth").check()
    assert _wait_for(lambda: settings.grooves == "smooth"), settings.grooves
    _radio(page, "auto").check()
    assert _wait_for(lambda: settings.grooves == "auto"), settings.grooves
