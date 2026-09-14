"""Tests for the self-updater (lp.update) and the release builder (lp.release).

Nothing here touches the network or GitHub: a fake fetch serves a release
listing, a manifest, and tarballs built in a temp dir, and pip is stubbed.
The properties that matter for a kiosk nobody sshes into:

  * a release is staged beside the running one and ``current`` flips last, so
    a failed download or a bad checksum leaves the running release untouched;
  * a cache family is downloaded only when one of its images changed;
  * an 'idle' install waits for the album to end before relaunching, and a
    'now' install does not;
  * a git checkout is not "managed" and never tries to swap itself.

    .venv/bin/python -m pytest tests/test_update.py
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lp import release, update
from lp.update import MANIFEST_NAME, UpdateError, UpdateManager, Updater


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _tar(path, members):
    """Write a .tar.gz of {name: bytes} to ``path``."""
    with tarfile.open(path, 'w:gz') as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


class FakeGitHub:
    """A release on disk plus a fetch() that serves it the way GitHub would."""

    def __init__(self, root, tag, cache=None, requirements=b'pygame-ce\n'):
        self.root = root
        self.tag = tag
        self.calls = []
        assets_dir = os.path.join(root, tag)
        os.makedirs(assets_dir)
        prefix = f'lp-{tag}/'
        source = f'lp-{tag}.tar.gz'
        _tar(os.path.join(assets_dir, source), {
            prefix + 'RELEASE': f'{tag}\n'.encode(),
            prefix + 'main.py': b'print("lp")\n',
            prefix + 'requirements.txt': requirements,
        })
        manifest = {'release': tag, 'title': tag, 'source': source, 'assets': {}, 'cache': {}}
        for family, files in (cache or {}).items():
            name = f'vinyl-cache-{family}.tar.gz'
            _tar(os.path.join(assets_dir, name), {f'{family}/{n}': d for n, d in files.items()})
            manifest['cache'][family] = {'asset': name,
                                         'files': {n: _sha(d) for n, d in files.items()}}
        for name in [source] + [c['asset'] for c in manifest['cache'].values()]:
            with open(os.path.join(assets_dir, name), 'rb') as f:
                data = f.read()
            manifest['assets'][name] = {'sha256': _sha(data), 'size': len(data)}
        self.manifest = manifest
        with open(os.path.join(assets_dir, MANIFEST_NAME), 'w') as f:
            json.dump(manifest, f)
        self.asset_names = [MANIFEST_NAME, source] + [c['asset'] for c in manifest['cache'].values()]

    def corrupt(self, name):
        with open(os.path.join(self.root, self.tag, name), 'ab') as f:
            f.write(b'garbage')

    def fetch(self, url, dest=None, progress=None, timeout=None):
        self.calls.append(url)
        if url.endswith('/releases/latest'):
            return {'tag_name': self.tag, 'name': self.tag.title(), 'body': 'notes',
                    'published_at': '2026-09-13T00:00:00Z', 'html_url': 'https://x/rel',
                    'assets': [{'name': n, 'browser_download_url': f'https://dl/{self.tag}/{n}'}
                               for n in self.asset_names]}
        name = url.rsplit('/', 1)[1]
        path = os.path.join(self.root, self.tag, name)
        if not os.path.isfile(path):
            raise UpdateError(f'{url}: HTTP 404')
        with open(path, 'rb') as f:
            data = f.read()
        if dest is None:
            return json.loads(data)
        with open(dest, 'wb') as f:
            f.write(data)
        if progress:
            progress(len(data), len(data))
        return dest


class Home:
    """An install root path that also remembers the pip calls made into it."""

    def __init__(self, path):
        self.path = path
        self.pip_calls = []

    def __truediv__(self, other):
        return self.path / other

    def __str__(self):
        return str(self.path)

    def __fspath__(self):
        return str(self.path)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An install root with a fake venv, and pip stubbed out."""
    home = Home(tmp_path / 'home')
    python = home / 'venv' / 'bin' / 'python'
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\n')
    # Stub subprocess for lp.update only (lp.release and the git helper below
    # need the real one): a fake module with run() recording the pip calls.
    fake = types.SimpleNamespace(
        run=lambda cmd, **kw: home.pip_calls.append(cmd) or subprocess.CompletedProcess(cmd, 0),
        CalledProcessError=subprocess.CalledProcessError)
    monkeypatch.setattr(update, 'subprocess', fake)
    return home


def _updater(home, gh):
    return Updater(str(home), fetch=gh.fetch)


def _installed_release(home):
    return (home / 'current' / 'RELEASE').read_text().strip()


# --- Updater -------------------------------------------------------------------

def test_a_first_install_stages_the_release_and_points_current_at_it(home, tmp_path):
    gh = FakeGitHub(tmp_path / 'gh', 'karmanjakah', cache={'nebula': {'a.png': b'A'}})
    u = _updater(home, gh)
    assert u.current_release() is None

    assert u.install() == 'karmanjakah'

    assert os.path.islink(home / 'current')
    assert os.readlink(home / 'current') == 'releases/karmanjakah'
    assert _installed_release(home) == 'karmanjakah'
    assert (home / 'releases' / 'karmanjakah' / 'main.py').exists()
    assert (home / 'cache' / 'nebula' / 'a.png').read_bytes() == b'A'
    assert not (home / 'tmp').exists(), 'downloads are cleaned up'
    assert any('pip' in c for c in home.pip_calls), 'requirements installed the first time'


def test_check_reports_an_update_only_when_the_tag_differs(home, tmp_path):
    gh = FakeGitHub(tmp_path / 'gh', 'karmanjakah')
    u = _updater(home, gh)
    u.install()
    assert u.available() is None, 'just installed the latest'

    newer = FakeGitHub(tmp_path / 'gh2', 'crucible-and-ruin')
    u._fetch = newer.fetch
    u.check()
    assert u.available() == 'crucible-and-ruin'
    assert u.latest['title'] == 'Crucible-And-Ruin'


def test_installing_the_current_release_again_is_refused(home, tmp_path):
    gh = FakeGitHub(tmp_path / 'gh', 'karmanjakah')
    u = _updater(home, gh)
    u.install()
    with pytest.raises(UpdateError, match='already installed'):
        u.install()
    u.install(force=True)       # explicit reinstall is fine
    assert _installed_release(home) == 'karmanjakah'


def test_a_bad_checksum_leaves_the_running_release_untouched(home, tmp_path):
    first = FakeGitHub(tmp_path / 'gh', 'karmanjakah')
    u = _updater(home, first)
    u.install()

    bad = FakeGitHub(tmp_path / 'gh2', 'crucible-and-ruin')
    bad.corrupt('lp-crucible-and-ruin.tar.gz')
    u._fetch = bad.fetch
    with pytest.raises(UpdateError, match='sha256 mismatch'):
        u.install()

    assert _installed_release(home) == 'karmanjakah'
    assert not (home / 'releases' / 'crucible-and-ruin').exists()
    assert not (home / 'releases' / '.crucible-and-ruin.partial').exists()


def test_a_missing_asset_is_reported_before_anything_is_downloaded(home, tmp_path):
    gh = FakeGitHub(tmp_path / 'gh', 'karmanjakah')
    gh.asset_names.remove('lp-karmanjakah.tar.gz')
    u = _updater(home, gh)
    with pytest.raises(UpdateError, match='missing asset'):
        u.install()
    assert not (home / 'releases').exists()


def test_only_changed_cache_families_are_downloaded(home, tmp_path):
    cache = {'mandelbrot': {'m.png': b'M'}, 'nebula': {'n.png': b'N'}}
    gh = FakeGitHub(tmp_path / 'gh', 'karmanjakah', cache=cache)
    u = _updater(home, gh)
    u.install()

    cache['nebula'] = {'n.png': b'N2'}          # teal-marble got retuned
    gh2 = FakeGitHub(tmp_path / 'gh2', 'crucible-and-ruin', cache=cache)
    u._fetch = gh2.fetch
    u.install()

    downloaded = [c.rsplit('/', 1)[1] for c in gh2.calls if 'vinyl-cache' in c]
    assert downloaded == ['vinyl-cache-nebula.tar.gz']
    assert (home / 'cache' / 'nebula' / 'n.png').read_bytes() == b'N2'
    assert (home / 'cache' / 'mandelbrot' / 'm.png').read_bytes() == b'M'


def test_pip_runs_only_when_requirements_change(home, tmp_path):
    gh = FakeGitHub(tmp_path / 'gh', 'karmanjakah', requirements=b'a\n')
    u = _updater(home, gh)
    u.install()
    n = len(home.pip_calls)
    assert n > 0

    same = FakeGitHub(tmp_path / 'gh2', 'crucible-and-ruin', requirements=b'a\n')
    u._fetch = same.fetch
    u.install()
    assert len(home.pip_calls) == n, 'unchanged requirements: no pip'

    changed = FakeGitHub(tmp_path / 'gh3', 'next', requirements=b'a\nb\n')
    u._fetch = changed.fetch
    u.install()
    assert len(home.pip_calls) > n


def test_older_releases_are_pruned_but_the_previous_one_is_kept(home, tmp_path):
    u = _updater(home, FakeGitHub(tmp_path / 'g1', 'one'))
    u.install()
    u._fetch = FakeGitHub(tmp_path / 'g2', 'two').fetch
    u.install()
    u._fetch = FakeGitHub(tmp_path / 'g3', 'three').fetch
    u.install()
    assert sorted(os.listdir(home / 'releases')) == ['three', 'two']


def test_a_tarball_that_escapes_its_folder_is_refused(home, tmp_path):
    gh = FakeGitHub(tmp_path / 'gh', 'evil')
    src = tmp_path / 'gh' / 'evil' / 'lp-evil.tar.gz'
    _tar(str(src), {'lp-evil/RELEASE': b'evil\n', 'lp-evil/../../owned': b'x'})
    gh.manifest['assets']['lp-evil.tar.gz']['sha256'] = _sha(src.read_bytes())
    with open(tmp_path / 'gh' / 'evil' / MANIFEST_NAME, 'w') as f:
        json.dump(gh.manifest, f)
    u = _updater(home, gh)
    with pytest.raises(UpdateError, match='refusing tar member'):
        u.install()
    assert not (tmp_path / 'owned').exists()


def test_a_release_without_a_manifest_is_not_offered(home, tmp_path):
    gh = FakeGitHub(tmp_path / 'gh', 'handmade')
    gh.asset_names.remove(MANIFEST_NAME)
    with pytest.raises(UpdateError, match='release workflow'):
        _updater(home, gh).check()


def test_a_git_checkout_is_not_managed(home, tmp_path):
    u = _updater(home, FakeGitHub(tmp_path / 'gh', 'one'))
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    assert not u.is_managed(str(checkout))
    u.install()
    assert not u.is_managed(str(checkout)), 'an install elsewhere changes nothing'
    assert u.is_managed(str(home / 'current'))
    assert u.is_managed(str(home / 'releases' / 'one'))


def test_relaunch_reuses_the_apps_arguments(home, tmp_path):
    u = _updater(home, FakeGitHub(tmp_path / 'gh', 'one'))
    u.install()
    argv = u.relaunch_argv(['/old/main.py', '-c', '/etc/lp.yml', '--no-open'])
    assert argv == [str(home / 'venv' / 'bin' / 'python'), str(home / 'current' / 'main.py'),
                    '-c', '/etc/lp.yml', '--no-open']


# --- UpdateManager -------------------------------------------------------------

class FakePlayer:
    def __init__(self, playing):
        self.playing = playing
        self.callbacks = {}
        self.shutdowns = 0

    def on(self, event, cb):
        self.callbacks.setdefault(event, []).append(cb)

    def get_status(self):
        return {'playing': self.playing}

    def shutdown(self):
        self.shutdowns += 1

    def end_album(self):
        self.playing = False
        for cb in self.callbacks.get('album_end', []):
            cb()


def _manager(home, gh, player, **kw):
    launched = []
    u = _updater(home, gh)
    m = UpdateManager({}, player, updater=u, argv=['main.py', '-c', 'x.yml'],
                      running_from=str(home / 'current'), relaunch=launched.append, **kw)
    m.launched = launched
    return m


def _settle(m):
    """Wait for the background install thread, if any."""
    t = m._thread
    if t is not None:
        t.join(timeout=10)
    for t in _threads_named(m):
        t.join(timeout=10)


def _threads_named(m):
    import threading
    return [t for t in threading.enumerate() if t is not threading.current_thread()
            and t.daemon and t.name.startswith('Thread-')]


def test_an_idle_install_waits_for_the_album_to_end(home, tmp_path):
    gh = FakeGitHub(tmp_path / 'gh', 'one')
    _updater(home, gh).install()
    player = FakePlayer(playing=True)
    m = _manager(home, FakeGitHub(tmp_path / 'gh2', 'two'), player)
    m.check()
    assert m.status()['available'] == 'two'

    m.install('idle')
    _settle(m)
    assert m.status()['state'] == 'ready'
    assert m.status()['installed'] == 'two'
    assert _installed_release(home) == 'two', 'staged and switched already'
    assert m.launched == [], 'but not relaunched: an album is playing'

    player.end_album()
    _settle(m)
    assert len(m.launched) == 1
    assert player.shutdowns == 1
    assert m.launched[0][1].endswith('current/main.py')


def test_a_now_install_relaunches_mid_album(home, tmp_path):
    _updater(home, FakeGitHub(tmp_path / 'gh', 'one')).install()
    player = FakePlayer(playing=True)
    m = _manager(home, FakeGitHub(tmp_path / 'gh2', 'two'), player)
    m.install('now')
    _settle(m)
    assert len(m.launched) == 1


def test_a_pending_restart_can_be_cancelled(home, tmp_path):
    _updater(home, FakeGitHub(tmp_path / 'gh', 'one')).install()
    player = FakePlayer(playing=True)
    m = _manager(home, FakeGitHub(tmp_path / 'gh2', 'two'), player)
    m.install('idle')
    _settle(m)
    m.install('cancel')
    player.end_album()
    _settle(m)
    assert m.launched == []
    assert m.status()['pending'] is None
    assert m.status()['installed'] == 'two', 'the staged release is still there'

    m.install('now')            # already staged: no second download, straight to relaunch
    _settle(m)
    assert len(m.launched) == 1


def test_a_failed_install_reports_the_error_and_keeps_running(home, tmp_path):
    _updater(home, FakeGitHub(tmp_path / 'gh', 'one')).install()
    bad = FakeGitHub(tmp_path / 'gh2', 'two')
    bad.corrupt('lp-two.tar.gz')
    m = _manager(home, bad, FakePlayer(playing=False))
    m.install('now')
    _settle(m)
    s = m.status()
    assert s['state'] == 'error'
    assert 'sha256' in s['error']
    assert s['pending'] is None
    assert m.launched == []
    assert _installed_release(home) == 'one'


def test_a_check_failure_is_reported_not_raised(home, tmp_path):
    def down(url, dest=None, progress=None, timeout=None):
        raise UpdateError('api.github.com: no route to host')
    u = Updater(str(home), fetch=down)
    m = UpdateManager({}, None, updater=u, argv=['main.py'], relaunch=lambda a: None)
    s = m.check()
    assert s['state'] == 'error'
    assert 'no route' in s['error']


def test_an_unmanaged_checkout_never_starts_the_loop(home, tmp_path):
    u = _updater(home, FakeGitHub(tmp_path / 'gh', 'one'))
    m = UpdateManager({}, None, updater=u, argv=['main.py'],
                      running_from=str(tmp_path), relaunch=lambda a: None)
    assert not m.managed
    m.start()
    assert m._loop_thread is None


# --- lp.release ------------------------------------------------------------------

def _git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                            GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t'))


def test_release_assets_round_trip_through_the_updater(tmp_path, home):
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init', '-q')
    (repo / 'main.py').write_text('print("lp")\n')
    (repo / 'requirements.txt').write_text('pygame-ce\n')
    (repo / 'lpcore' / 'cache' / 'nebula').mkdir(parents=True)
    (repo / 'lpcore' / 'cache' / 'nebula' / 'committed.png').write_bytes(b'PNG')
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-q', '-m', 'init')
    _git(repo, 'tag', 'crucible-and-ruin')
    cache = tmp_path / 'cache'
    (cache / 'nebula').mkdir(parents=True)
    (cache / 'nebula' / 'teal-marble.png').write_bytes(b'PNG')
    (cache / 'nebula' / '.teal.part.png').write_bytes(b'half')     # never shipped

    out = tmp_path / 'dist'
    manifest = release.build('crucible-and-ruin', str(out), cache_root=str(cache),
                             repo=str(repo), log=lambda *_: None)

    assert manifest['title'] == 'Crucible & Ruin'
    assert manifest['source'] == 'lp-crucible-and-ruin.tar.gz'
    assert list(manifest['cache']) == ['nebula'], 'families with no images are left out'
    assert manifest['cache']['nebula']['files'] == {'teal-marble.png': _sha(b'PNG')}
    with tarfile.open(out / 'lp-crucible-and-ruin.tar.gz') as tar:
        names = tar.getnames()
        assert 'lp-crucible-and-ruin/RELEASE' in names
        assert tar.extractfile('lp-crucible-and-ruin/RELEASE').read() == b'crucible-and-ruin\n'
        assert not [n for n in names if '/lpcore/cache/' in n], \
            'the committed images ship in the cache tarballs, not the source'
    written = json.load(open(out / MANIFEST_NAME))
    assert written == manifest

    # The updater can install exactly what the builder produced.
    class Serve:
        calls = []

        def fetch(self, url, dest=None, progress=None, timeout=None):
            if url.endswith('/releases/latest'):
                return {'tag_name': 'crucible-and-ruin', 'name': 'Crucible & Ruin',
                        'assets': [{'name': n, 'browser_download_url': f'https://dl/{n}'}
                                   for n in os.listdir(out)]}
            path = out / url.rsplit('/', 1)[1]
            if dest is None:
                return json.load(open(path))
            with open(path, 'rb') as src, open(dest, 'wb') as dst:
                dst.write(src.read())
            return dest

    u = Updater(str(home), fetch=Serve().fetch)
    assert u.install() == 'crucible-and-ruin'
    assert (home / 'releases' / 'crucible-and-ruin' / 'main.py').read_text() == 'print("lp")\n'
    assert (home / 'cache' / 'nebula' / 'teal-marble.png').read_bytes() == b'PNG'
    assert not (home / 'cache' / 'nebula' / '.teal.part.png').exists()
