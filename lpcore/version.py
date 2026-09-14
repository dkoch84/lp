"""Release/version reporting for the running checkout.

The canonical release name is the most recent annotated/lightweight tag (lp
ships named releases like ``crucible-and-ruin``). We derive it from git so a deploy
box reports exactly what it has checked out. A release tarball (built by
``lp.release`` and installed by ``lp.update``) has no git metadata, so it carries
a ``RELEASE`` file at its root naming the tag; RELEASE_NAME is the last resort
when neither exists.
"""
import functools
import os
import subprocess

# Bumped per release; used when git metadata isn't available at runtime.
RELEASE_NAME = 'ruin'

# How a release's tag reads in the web UI (tags can't hold spaces or '&').
RELEASE_TITLES = {
    'karmanjakah': 'Karmanjakah',
    'crucible-and-ruin': 'Crucible & Ruin',
    'crucible': 'Crucible',
    'ruin': 'Ruin',
}

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE_FILE = os.path.join(_REPO_DIR, 'RELEASE')


def _stamped_release():
    """The tag named by the RELEASE file a release tarball ships with, or None."""
    try:
        with open(RELEASE_FILE) as f:
            name = f.read().strip()
    except OSError:
        return None
    return name or None


def _git(*args):
    try:
        out = subprocess.run(
            ['git', '-C', _REPO_DIR, *args],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


@functools.lru_cache(maxsize=1)
def get_version():
    """Return release info for the running checkout.

    ``release``  — newest tag name (the named release), or RELEASE_NAME.
    ``describe`` — ``git describe`` (tag, commits-ahead, short sha, +dirty).
    ``commit``   — short commit sha, when available.
    ``title``    — how the release reads, e.g. ``Crucible & Ruin``.
    """
    stamped = _stamped_release()
    release = stamped or _git('describe', '--tags', '--abbrev=0') or RELEASE_NAME
    describe = stamped or _git('describe', '--tags', '--always', '--dirty') or release
    commit = None if stamped else _git('rev-parse', '--short', 'HEAD')
    return {'release': release, 'describe': describe, 'commit': commit,
            'title': release_title(release)}


def release_title(tag):
    """How a tag reads to people: ``crucible-and-ruin`` is ``Crucible & Ruin``."""
    return RELEASE_TITLES.get(tag, tag)
