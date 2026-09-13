"""Tests for lp-deck's vinyl chooser swatches.

Swatches that show album art (the "Album Art" picture disc and the "Album art"
label) must draw the playing album's real cover, or the choice is invisible:
drawn without art they fall back to a plain black disc. Every other swatch
must stay independent of the album so it's rendered once and reused.

    .venv/bin/python -m pytest tests/test_lpdeck_vinyl_preview.py
"""
import os
import sys

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip('PySide6', reason='lp-deck needs PySide6 (requirements-deck.txt)')

import pygame
from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication

from lpdeck import db, qmlapp, vinyl_preview

EDGE = 48


@pytest.fixture(scope='module')
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def cover(tmp_path):
    pygame.init()
    surf = pygame.Surface((64, 64))
    surf.fill((220, 30, 40))
    path = str(tmp_path / 'cover.png')
    pygame.image.save(surf, path)
    return path


def _bits(img):
    return bytes(img.constBits())


@pytest.mark.parametrize('style,label', [('picture', 'label-white'), ('black', 'art')])
def test_album_art_swatches_draw_the_cover(app, cover, style, label):
    plain = vinyl_preview.preview(style, label, EDGE)
    with_art = vinyl_preview.preview(style, label, EDGE, art_path=cover)
    assert _bits(plain) != _bits(with_art)


@pytest.fixture
def provider(tmp_path, monkeypatch, cover):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    db_path = str(tmp_path / 'library.db')
    con = db.connect(db_path)
    aid = con.execute("INSERT INTO artists(name, sort_name) VALUES ('A', 'a')").lastrowid
    album = con.execute("INSERT INTO albums(artist_id, name, path, cover_path) VALUES (?,?,?,?)",
                        (aid, 'Album', '/music/A/Album', cover)).lastrowid
    con.commit()
    con.close()
    return qmlapp.VinylPreviewProvider(db_path), album, tmp_path / 'cache' / 'lp-deck' / 'vinyl-previews'


def _request(p, image_id):
    return p.requestImage(image_id, QSize(), QSize(EDGE, EDGE))


def test_provider_draws_the_albums_cover(app, provider):
    p, album, _cache = provider
    art_less = _request(p, 'picture~label-white')
    with_album = _request(p, f'picture~label-white~{album}')
    assert _bits(art_less) != _bits(with_album)


def test_provider_caches_album_swatches_per_album(app, provider):
    p, album, cache = provider
    _request(p, f'picture~art~{album}')
    names = os.listdir(cache)
    assert f'picture_art_album{album}_{EDGE}.png' in names
    assert _bits(_request(p, f'picture~art~{album}')) == _bits(_request(p, f'picture~art~{album}'))


def test_unknown_album_falls_back_to_the_plain_swatch(app, provider):
    p, _album, _cache = provider
    assert _bits(_request(p, 'picture~label-white~99999')) == _bits(_request(p, 'picture~label-white'))
    assert _bits(_request(p, 'picture~label-white~not-a-number')) == _bits(_request(p, 'picture~label-white'))
