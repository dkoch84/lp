"""Tests for the vinyl preview images the web UI shows.

Previews were served as immutable for a year. A style keeps its id when it is
retuned, so after purple-marble and pink-marble were recoloured the web UI kept
showing the old pictures while the kiosk drew the new ones. Now every request
revalidates: an unchanged image answers 304 with no body, and a replaced one
comes back in full.

    .venv/bin/python -m pytest tests/test_api_vinyl_preview.py
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lp.api import create_app
from lpcore.vinyl import cache
from test_api_play import _Library, _Player

URL = '/api/vinyl/preview/test-marble'
VINYL_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'static', 'vinyl.html')


@pytest.fixture
def rig(tmp_path, monkeypatch):
    nebula = tmp_path / 'nebula'
    nebula.mkdir()
    monkeypatch.setattr(cache, 'NEBULA_CACHE_DIR', str(nebula))
    image = nebula / 'test-marble.png'
    image.write_bytes(b'old picture')
    return TestClient(create_app(_Player(), _Library(), '/nonexistent')), image


def test_previews_revalidate_instead_of_being_immutable(rig):
    client, _ = rig
    r = client.get(URL)
    assert r.status_code == 200 and r.content == b'old picture'
    assert r.headers['cache-control'] == 'no-cache'
    assert r.headers['etag']


def test_an_unchanged_preview_answers_304(rig):
    client, _ = rig
    etag = client.get(URL).headers['etag']
    r = client.get(URL, headers={'If-None-Match': etag})
    assert r.status_code == 304 and r.content == b''


def test_a_replaced_preview_comes_back_in_full(rig):
    client, image = rig
    etag = client.get(URL).headers['etag']
    image.write_bytes(b'new picture, retuned')
    later = image.stat().st_mtime_ns + 10**9
    os.utime(image, ns=(later, later))
    r = client.get(URL, headers={'If-None-Match': etag})
    assert r.status_code == 200 and r.content == b'new picture, retuned'
    assert r.headers['etag'] != etag


def test_a_missing_preview_is_a_404(rig):
    client, _ = rig
    assert client.get('/api/vinyl/preview/no-such-style').status_code == 404


def test_the_web_ui_leaves_the_old_year_long_entries_behind():
    with open(VINYL_HTML) as f:
        assert '/api/vinyl/preview/${s.slice(pfx.length)}?r=2' in f.read()
