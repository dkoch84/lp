"""Release/version reporting for the running checkout.

The canonical release name is the most recent annotated/lightweight tag (lp
ships named releases like ``karmanjakah``). We derive it from git so a deploy
box reports exactly what it has checked out, falling back to RELEASE_NAME when
git isn't available (e.g. a tarball deploy).
"""
import functools
import os
import subprocess

# Bumped per release; used when git metadata isn't available at runtime.
RELEASE_NAME = 'karmanjakah'

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    """
    release = _git('describe', '--tags', '--abbrev=0') or RELEASE_NAME
    describe = _git('describe', '--tags', '--always', '--dirty') or release
    commit = _git('rev-parse', '--short', 'HEAD')
    return {'release': release, 'describe': describe, 'commit': commit}
