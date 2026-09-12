"""Tests for lp.display.fit_text — the kiosk's text ellipsizer.

The point: the kiosk metadata panel is fixed-width and read from across a room,
and song titles are the one field that regularly outruns it. fit_text is what
keeps a long title from sliding off the panel edge, and the property that
matters is not "it looks right" but "the result always renders within max_w".
Every test below asserts that by MEASURING the result with the same font, so it
holds for any font the kiosk happens to load.

Uses pygame's built-in font rather than a system font, so the numbers do not
move with whatever fontconfig serves on the machine running the tests.

    .venv/bin/python -m pytest tests/test_display_text.py
"""
import os
import sys

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lp.display import fit_text

ELLIPSIS = '…'
LONG = "Devoid of Redemption (Reprise) in the Key of Endless Sorrow, Part Two"


@pytest.fixture(scope="module")
def font():
    pygame.init()
    pygame.font.init()
    return pygame.font.Font(None, 28)


def test_text_that_fits_is_returned_untouched(font):
    text = "Rite of Ruin"
    assert fit_text(font, text, font.size(text)[0] + 50) == text


def test_text_at_exactly_the_limit_is_untouched(font):
    text = "Rite of Ruin"
    assert fit_text(font, text, font.size(text)[0]) == text


def test_long_text_is_ellipsized(font):
    got = fit_text(font, LONG, 200)
    assert got != LONG
    assert got.endswith(ELLIPSIS)
    assert LONG.startswith(got[:-1].rstrip())


@pytest.mark.parametrize("max_w", [40, 80, 150, 200, 320, 500, 700])
def test_result_always_renders_within_the_limit(font, max_w):
    """The one property the caller depends on."""
    got = fit_text(font, LONG, max_w)
    assert font.size(got)[0] <= max_w, f"{got!r} overflows {max_w}px"


def test_result_uses_the_space_available(font):
    """Not just correct but not needlessly short: one more character would
    overflow."""
    max_w = 300
    got = fit_text(font, LONG, max_w)
    assert got.endswith(ELLIPSIS)
    kept = len(got) - 1
    assert font.size(LONG[:kept + 1] + ELLIPSIS)[0] > max_w


def test_more_room_never_yields_less_text(font):
    """Monotonic in max_w, which is what makes the bisection valid."""
    lengths = [len(fit_text(font, LONG, w)) for w in range(60, 700, 20)]
    assert lengths == sorted(lengths)


def test_trailing_space_is_stripped_before_the_ellipsis(font):
    """'Endless …' reads as a typo; 'Endless…' does not."""
    got = fit_text(font, "Sorrow Endless Reprise", 10_000)
    assert got == "Sorrow Endless Reprise"
    for max_w in range(30, 260, 3):
        got = fit_text(font, "Sorrow Endless Reprise", max_w)
        assert not got.endswith(' ' + ELLIPSIS)


def test_zero_or_negative_width_yields_nothing(font):
    assert fit_text(font, LONG, 0) == ''
    assert fit_text(font, LONG, -20) == ''


def test_width_too_small_even_for_the_ellipsis_yields_nothing(font):
    assert fit_text(font, LONG, 1) == ''


def test_empty_text_is_returned_as_is(font):
    assert fit_text(font, '', 500) == ''
    assert fit_text(font, None, 500) is None


def test_unicode_title_is_handled(font):
    text = "Ágætis byrjun (Sigur Rós) Þessi Söngur Er Mjög Langur Titill Hér"
    got = fit_text(font, text, 200)
    assert font.size(got)[0] <= 200
    assert got.endswith(ELLIPSIS)
