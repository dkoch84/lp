"""Tests for release reporting: a release's tag and how its name reads.

Tags can't hold spaces or an ampersand, so the web UI shows a release's title
(``Crucible & Ruin``) rather than its tag (``crucible-and-ruin``).

    .venv/bin/python -m pytest tests/test_version.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore import version


def _version(monkeypatch, tag):
    answers = {'describe': tag, 'rev-parse': 'abc1234'}
    monkeypatch.setattr(version, '_git', lambda *args: answers.get(args[0]))
    version.get_version.cache_clear()
    try:
        return version.get_version()
    finally:
        version.get_version.cache_clear()


def test_the_current_release_reads_as_its_title(monkeypatch):
    v = _version(monkeypatch, 'crucible-and-ruin')
    assert v['release'] == 'crucible-and-ruin'
    assert v['title'] == 'Crucible & Ruin'


def test_without_git_the_built_in_release_is_reported(monkeypatch):
    v = _version(monkeypatch, None)
    assert v['release'] == version.RELEASE_NAME == 'crucible'
    assert v['title'] == 'Crucible'


def test_an_unknown_tag_reads_as_itself(monkeypatch):
    assert _version(monkeypatch, 'some-future-tag')['title'] == 'some-future-tag'
