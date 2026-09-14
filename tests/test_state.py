"""Tests for lp.state.UserState — recently played albums and persistence.

Standalone (no pytest needed):
    .venv/bin/python tests/test_state.py
or under pytest if installed:
    .venv/bin/python -m pytest tests/test_state.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lp.state import UserState, RECENT_ALBUMS_LIMIT


def _state():
    d = tempfile.mkdtemp(prefix='lp-state-')
    return UserState(os.path.join(d, 'state.json'))


def test_recent_empty():
    s = _state()
    assert s.get_recent_albums() == []


def test_recent_orders_most_recent_first():
    s = _state()
    s.mark_album_played('A', 'a1')
    s.mark_album_played('B', 'b1')
    s.mark_album_played('C', 'c1')
    got = [(e['artist'], e['folder']) for e in s.get_recent_albums()]
    assert got == [('C', 'c1'), ('B', 'b1'), ('A', 'a1')]


def test_recent_dedupes_and_promotes():
    s = _state()
    s.mark_album_played('A', 'a1')
    s.mark_album_played('B', 'b1')
    s.mark_album_played('A', 'a1')  # replay → back to the top, no dup
    got = [(e['artist'], e['folder']) for e in s.get_recent_albums()]
    assert got == [('A', 'a1'), ('B', 'b1')]


def test_recent_caps_at_limit():
    s = _state()
    for i in range(RECENT_ALBUMS_LIMIT + 5):
        s.mark_album_played('A', f'album-{i}')
    recent = s.get_recent_albums()
    assert len(recent) == RECENT_ALBUMS_LIMIT
    # Newest kept, oldest evicted.
    assert recent[0]['folder'] == f'album-{RECENT_ALBUMS_LIMIT + 4}'
    folders = {e['folder'] for e in recent}
    assert 'album-0' not in folders


def test_recent_ignores_blank_entries():
    s = _state()
    s.mark_album_played('', 'x')
    s.mark_album_played('A', '')
    s.mark_album_played(None, None)
    assert s.get_recent_albums() == []


def test_recent_persists_across_reload():
    s = _state()
    s.mark_album_played('A', 'a1')
    s.mark_album_played('B', 'b1')
    reloaded = UserState(s.path)
    got = [(e['artist'], e['folder']) for e in reloaded.get_recent_albums()]
    assert got == [('B', 'b1'), ('A', 'a1')]


def test_recent_remove_takes_an_album_off_and_reports_it():
    s = _state()
    s.mark_album_played('A', 'a1')
    s.mark_album_played('B', 'b1')
    assert s.remove_recent_album('A', 'a1') is True
    assert [(e['artist'], e['folder']) for e in s.get_recent_albums()] == [('B', 'b1')]
    assert s.remove_recent_album('A', 'a1') is False, 'already gone'
    reloaded = UserState(s.path)
    assert [(e['artist'], e['folder']) for e in reloaded.get_recent_albums()] == [('B', 'b1')]


def test_get_recent_returns_copies():
    s = _state()
    s.mark_album_played('A', 'a1')
    got = s.get_recent_albums()
    got[0]['artist'] = 'MUTATED'
    assert s.get_recent_albums()[0]['artist'] == 'A'


def test_vinyl_favorites_empty():
    s = _state()
    assert s.get_vinyl_favorites() == []
    assert s.is_vinyl_favorite('color-red') is False


def test_vinyl_favorites_add_and_remove():
    s = _state()
    s.set_vinyl_favorite('color-red', True)
    s.set_vinyl_favorite('mandelbrot-seahorse-purple', True)
    assert s.is_vinyl_favorite('color-red') is True
    assert s.get_vinyl_favorites() == ['color-red', 'mandelbrot-seahorse-purple']
    s.set_vinyl_favorite('color-red', False)
    assert s.is_vinyl_favorite('color-red') is False
    assert s.get_vinyl_favorites() == ['mandelbrot-seahorse-purple']


def test_vinyl_favorites_idempotent():
    s = _state()
    s.set_vinyl_favorite('nebula-lava-lamp', True)
    s.set_vinyl_favorite('nebula-lava-lamp', True)  # no duplicate
    assert s.get_vinyl_favorites() == ['nebula-lava-lamp']
    s.set_vinyl_favorite('nebula-lava-lamp', False)
    s.set_vinyl_favorite('nebula-lava-lamp', False)  # already gone, no error
    assert s.get_vinyl_favorites() == []


def test_vinyl_favorites_persist_across_reload():
    s = _state()
    s.set_vinyl_favorite('color-teal', True)
    s.set_vinyl_favorite('munafo-deep5_v1', True)
    reloaded = UserState(s.path)
    assert reloaded.get_vinyl_favorites() == ['color-teal', 'munafo-deep5_v1']


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"test_state: {len(tests)} passed")


if __name__ == '__main__':
    _run()
