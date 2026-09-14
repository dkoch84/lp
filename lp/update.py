"""Self-update for a release install of lp.

A kiosk nobody wants to ssh into keeps its releases under one folder:

    ~/lp/
      releases/<tag>/     an unpacked release tarball (RELEASE file names it)
      current -> releases/<tag>
      venv/               one shared virtualenv (pip runs only when
                          requirements.txt changes between releases)
      cache/              the rendered vinyl images, shared across releases
      data/               state files (favorites, port, Last.fm session)
      tmp/                downloads in flight

The systemd user unit runs ``venv/bin/python current/main.py`` with
LP_HOME/LP_CACHE_DIR/LP_DATA_DIR pointing into that layout. An update is then:
download the next release's assets, unpack them beside the running one, swap
the ``current`` symlink, and relaunch. The running release is never modified,
a failed download leaves it untouched, and rolling back is pointing ``current``
at the previous folder.

This module deliberately imports nothing outside the standard library: the
installer runs it with the system python3 before a virtualenv exists
(``python3 update.py bootstrap``), and the web API drives it from inside the
app. Everything the app needs to know about updates goes through
:class:`UpdateManager`; :class:`Updater` is the file-and-network half and has
no idea a player exists.

    python -m lp.update status            # what's installed, what's latest
    python -m lp.update check             # ask GitHub (no install)
    python -m lp.update install           # fetch + stage the latest release
    python -m lp.update bootstrap --home ~/lp    # first install, from nothing
"""
import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request

GITHUB_REPO = 'dkoch84/lp'
MANIFEST_NAME = 'release-manifest.json'
USER_AGENT = 'lp-updater (+https://github.com/dkoch84/lp)'
KEEP_RELEASES = 2          # current + the one before it, for rollback
DEFAULT_CHECK_HOURS = 6
UNIT_NAME = 'lp'           # the systemd user unit deploy/lp.service installs

log = logging.getLogger('lp.update')


class UpdateError(Exception):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def default_home():
    return os.environ.get('LP_HOME') or os.path.join(os.path.expanduser('~'), 'lp')


def _http_get(url, dest=None, progress=None, timeout=30):
    """GET ``url``. Returns parsed JSON when ``dest`` is None, else streams the
    body to ``dest`` (calling ``progress(done, total)``) and returns dest."""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT,
                                               'Accept': 'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if dest is None:
                return json.loads(resp.read().decode('utf-8'))
            total = int(resp.headers.get('Content-Length') or 0)
            done = 0
            with open(dest, 'wb') as out:
                for chunk in iter(lambda: resp.read(1 << 18), b''):
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
            return dest
    except urllib.error.HTTPError as e:
        raise UpdateError(f'{url}: HTTP {e.code}') from e
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f'{url}: {getattr(e, "reason", e)}') from e


class Updater:
    """Files and network. Knows the install layout, not the app."""

    def __init__(self, home=None, repo=GITHUB_REPO, fetch=_http_get):
        self.home = os.path.abspath(home or default_home())
        self.repo = repo
        self._fetch = fetch
        self.latest = None          # last release seen by check()
        self.checked_at = None
        self.progress = {}          # {'phase', 'asset', 'done', 'total'}

    # --- layout -----------------------------------------------------------

    @property
    def releases_dir(self):
        return os.path.join(self.home, 'releases')

    @property
    def current_link(self):
        return os.path.join(self.home, 'current')

    @property
    def venv_dir(self):
        return os.path.join(self.home, 'venv')

    @property
    def cache_dir(self):
        return os.path.join(self.home, 'cache')

    @property
    def data_dir(self):
        return os.path.join(self.home, 'data')

    @property
    def tmp_dir(self):
        return os.path.join(self.home, 'tmp')

    def python(self):
        return os.path.join(self.venv_dir, 'bin', 'python')

    def release_dir(self, tag):
        return os.path.join(self.releases_dir, tag)

    def current_release(self):
        """Tag ``current`` points at (from its RELEASE stamp), or None."""
        try:
            with open(os.path.join(self.current_link, 'RELEASE')) as f:
                return f.read().strip() or None
        except OSError:
            return None

    def is_managed(self, running_from=None):
        """True when ``running_from`` (default: this file's checkout) is a
        release under this home, so swapping ``current`` is meaningful. A git
        checkout run by hand is not managed: it updates with git pull."""
        running_from = running_from or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            real = os.path.realpath(running_from)
            return (os.path.islink(self.current_link)
                    and real.startswith(os.path.realpath(self.releases_dir) + os.sep))
        except OSError:
            return False

    def env(self):
        """Environment a release install runs under."""
        return {'LP_HOME': self.home, 'LP_CACHE_DIR': self.cache_dir,
                'LP_DATA_DIR': self.data_dir}

    # --- github ------------------------------------------------------------

    def check(self):
        """Ask GitHub for the latest release. Returns a summary dict."""
        data = self._fetch(f'https://api.github.com/repos/{self.repo}/releases/latest')
        assets = {a['name']: a['browser_download_url'] for a in data.get('assets', [])}
        if MANIFEST_NAME not in assets:
            raise UpdateError(f"release {data.get('tag_name')} has no {MANIFEST_NAME}; "
                              "it was not built by the release workflow")
        self.latest = {
            'tag': data['tag_name'],
            'title': data.get('name') or data['tag_name'],
            'notes': data.get('body') or '',
            'published_at': data.get('published_at'),
            'url': data.get('html_url'),
            'assets': assets,
        }
        self.checked_at = time.time()
        return self.latest

    def available(self):
        """The latest tag when it differs from what is installed, else None."""
        if not self.latest:
            return None
        return self.latest['tag'] if self.latest['tag'] != self.current_release() else None

    # --- install -----------------------------------------------------------

    def _download(self, name, url, expect=None):
        os.makedirs(self.tmp_dir, exist_ok=True)
        dest = os.path.join(self.tmp_dir, name)

        def progress(done, total):
            self.progress = {'phase': 'downloading', 'asset': name, 'done': done, 'total': total}

        self._fetch(url, dest, progress)
        if expect:
            got = sha256_file(dest)
            if got != expect['sha256']:
                os.unlink(dest)
                raise UpdateError(f'{name}: sha256 mismatch (got {got[:12]}, '
                                  f'manifest says {expect["sha256"][:12]})')
        return dest

    @staticmethod
    def _safe_members(tar, strip=0):
        """Members of ``tar`` with ``strip`` leading path parts removed, refusing
        anything that would land outside the extraction folder."""
        for m in tar:
            parts = m.name.split('/')
            if len(parts) <= strip:
                continue
            rel = '/'.join(parts[strip:])
            if rel.startswith('/') or '..' in parts or m.islnk() or m.issym():
                raise UpdateError(f'refusing tar member {m.name!r}')
            m.name = rel
            yield m

    def _extract(self, tarball, dest, strip=0):
        with tarfile.open(tarball, 'r:gz') as tar:
            tar.extractall(dest, members=self._safe_members(tar, strip))

    def _stage_source(self, tag, manifest, assets):
        name = manifest['source']
        tarball = self._download(name, assets[name], manifest['assets'][name])
        partial = self.release_dir(f'.{tag}.partial')
        shutil.rmtree(partial, ignore_errors=True)
        self.progress = {'phase': 'unpacking', 'asset': name}
        self._extract(tarball, partial, strip=1)      # drop the lp-<tag>/ prefix
        stamp = os.path.join(partial, 'RELEASE')
        if not os.path.isfile(stamp):
            raise UpdateError(f'{name} has no RELEASE stamp')
        final = self.release_dir(tag)
        shutil.rmtree(final, ignore_errors=True)
        os.replace(partial, final)
        os.unlink(tarball)
        return final

    def _cache_family_current(self, family, files):
        folder = os.path.join(self.cache_dir, family)
        for name, digest in files.items():
            path = os.path.join(folder, name)
            if not os.path.isfile(path) or sha256_file(path) != digest:
                return False
        return True

    def sync_cache(self, manifest, assets):
        """Bring ``cache/`` up to the manifest, one family tarball at a time,
        skipping families whose every image already matches. Images land via
        os.replace so a running renderer never opens a half-written file."""
        fetched = []
        for family, entry in manifest.get('cache', {}).items():
            if self._cache_family_current(family, entry['files']):
                continue
            name = entry['asset']
            tarball = self._download(name, assets[name], manifest['assets'][name])
            partial = os.path.join(self.cache_dir, f'.{family}.partial')
            shutil.rmtree(partial, ignore_errors=True)
            self.progress = {'phase': 'unpacking', 'asset': name}
            self._extract(tarball, partial)
            target = os.path.join(self.cache_dir, family)
            os.makedirs(target, exist_ok=True)
            for image in os.listdir(os.path.join(partial, family)):
                os.replace(os.path.join(partial, family, image), os.path.join(target, image))
            shutil.rmtree(partial, ignore_errors=True)
            os.unlink(tarball)
            fetched.append(family)
        return fetched

    def ensure_venv(self):
        if os.path.isfile(self.python()):
            return
        self.progress = {'phase': 'creating venv'}
        subprocess.run([sys.executable, '-m', 'venv', self.venv_dir], check=True)

    def install_requirements(self, release_dir):
        """pip install the release's requirements, only when they changed."""
        req = os.path.join(release_dir, 'requirements.txt')
        marker = os.path.join(self.venv_dir, '.requirements.sha256')
        digest = sha256_file(req)
        try:
            with open(marker) as f:
                if f.read().strip() == digest:
                    return False
        except OSError:
            pass
        self.progress = {'phase': 'installing dependencies'}
        pip = [self.python(), '-m', 'pip', 'install', '--quiet', '--upgrade', 'pip']
        subprocess.run(pip, check=True)
        subprocess.run([self.python(), '-m', 'pip', 'install', '--quiet', '-r', req], check=True)
        with open(marker, 'w') as f:
            f.write(digest + '\n')
        return True

    def switch(self, tag):
        """Point ``current`` at ``releases/<tag>`` atomically."""
        if not os.path.isdir(self.release_dir(tag)):
            raise UpdateError(f'release {tag} is not installed')
        new = self.current_link + '.new'
        if os.path.lexists(new):
            os.unlink(new)
        os.symlink(os.path.join('releases', tag), new)
        os.replace(new, self.current_link)

    def prune(self, keep):
        """Delete installed releases other than ``keep`` (tags), oldest first,
        so rollback material stays but the disk does not fill."""
        if not os.path.isdir(self.releases_dir):
            return []
        removed = []
        for name in sorted(os.listdir(self.releases_dir)):
            path = os.path.join(self.releases_dir, name)
            if name in keep or not os.path.isdir(path):
                continue
            shutil.rmtree(path, ignore_errors=True)
            removed.append(name)
        return removed

    def install(self, tag=None, force=False):
        """Fetch and stage the latest release (or ``tag``), leaving ``current``
        pointing at it. Returns the installed tag. Does not restart anything."""
        self.check()            # always fresh: one cheap call, never a stale listing
        if tag and self.latest['tag'] != tag:
            raise UpdateError(f'only the latest release ({self.latest["tag"]}) can be installed')
        tag = self.latest['tag']
        previous = self.current_release()
        if tag == previous and not force:
            raise UpdateError(f'{tag} is already installed')

        assets = self.latest['assets']
        self.progress = {'phase': 'downloading', 'asset': MANIFEST_NAME}
        manifest = self._fetch(assets[MANIFEST_NAME])
        if manifest.get('release') != tag:
            raise UpdateError(f'manifest is for {manifest.get("release")}, release is {tag}')
        for name in [manifest['source']] + [c['asset'] for c in manifest['cache'].values()]:
            if name not in assets:
                raise UpdateError(f'release {tag} is missing asset {name}')

        os.makedirs(self.releases_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        release_dir = self._stage_source(tag, manifest, assets)
        self.sync_cache(manifest, assets)
        self.ensure_venv()
        self.install_requirements(release_dir)
        self.switch(tag)
        keep = {tag} | ({previous} if previous else set())
        self.prune(keep)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        self.progress = {'phase': 'installed', 'tag': tag}
        return tag

    def relaunch_argv(self, argv):
        """The command that runs ``current``: same interpreter role, same
        arguments, new code. ``argv`` is sys.argv of the running app."""
        main = os.path.join(self.current_link, 'main.py')
        return [self.python(), main] + list(argv[1:])


class UpdateManager:
    """The app's view of updates: a periodic check, an install that can wait
    for the album to end, and the relaunch. Thread-safe; the API thread calls
    in, the player fires ``album_end`` on its own thread."""

    def __init__(self, config=None, player=None, updater=None, argv=None,
                 running_from=None, relaunch=None):
        config = config or {}
        self.updater = updater or Updater()
        self.player = player
        self.argv = list(argv if argv is not None else sys.argv)
        self.managed = self.updater.is_managed(running_from)
        self.auto = bool(config.get('auto', True))
        self.check_hours = float(config.get('check_hours', DEFAULT_CHECK_HOURS))
        self._relaunch = relaunch or self._exec_current
        self._lock = threading.Lock()
        self.state = 'idle'         # idle | checking | installing | ready | error
        self.error = None
        self.pending = None         # None | 'now' | 'idle': restart policy once ready
        self.installed = None       # tag staged and waiting for a restart
        self._stop = threading.Event()
        self._thread = None
        if player is not None:
            player.on('album_end', self._on_album_end)

    # --- reporting ---------------------------------------------------------

    def status(self):
        u = self.updater
        latest = u.latest or {}
        current = u.current_release()
        try:                                    # the app has lpcore; the bare installer does not
            from lpcore.version import release_title
        except ImportError:
            def release_title(tag):
                return tag
        return {
            'managed': self.managed,
            'auto': self.auto,
            'current': current,
            'current_title': release_title(current) if current else None,
            'latest': latest.get('tag'),
            'latest_title': latest.get('title'),
            'notes': latest.get('notes'),
            'published_at': latest.get('published_at'),
            'url': latest.get('url'),
            'available': u.available(),
            'checked_at': u.checked_at,
            'state': self.state,
            'error': self.error,
            'pending': self.pending,
            'installed': self.installed,
            'progress': dict(u.progress),
        }

    # --- actions -----------------------------------------------------------

    def check(self):
        """Synchronous check; returns status(). Errors land in status().error."""
        with self._lock:
            if self.state == 'installing':
                return self.status()
            self.state, self.error = 'checking', None
        try:
            self.updater.check()
            with self._lock:
                if self.state == 'checking':
                    self.state = 'ready' if self.installed else 'idle'
        except UpdateError as e:
            log.warning('update check failed: %s', e)
            with self._lock:
                self.state, self.error = 'error', str(e)
        return self.status()

    def install(self, when='idle'):
        """Download and stage the latest release in the background, then
        restart per ``when``: 'now', or 'idle' (once nothing is playing).
        'cancel' drops a pending restart (the staged release stays)."""
        if when == 'cancel':
            with self._lock:
                self.pending = None
            return self.status()
        if when not in ('now', 'idle'):
            raise ValueError(f'when must be now, idle or cancel, not {when!r}')
        with self._lock:
            self.pending = when
            if self.state == 'installing':
                return self.status()
            if self.installed and self.installed == (self.updater.latest or {}).get('tag'):
                self.state = 'ready'
            else:
                self.state, self.error = 'installing', None
                self._thread = threading.Thread(target=self._install_worker, daemon=True)
                self._thread.start()
                return self.status()
        self._maybe_restart()
        return self.status()

    def _install_worker(self):
        try:
            tag = self.updater.install()
            with self._lock:
                self.installed, self.state = tag, 'ready'
            log.info('update: %s staged, restart %s', tag, self.pending)
        except (UpdateError, subprocess.CalledProcessError, OSError) as e:
            log.error('update install failed: %s', e)
            with self._lock:
                self.state, self.error, self.pending = 'error', str(e), None
            return
        self._maybe_restart()

    def _playing(self):
        if self.player is None:
            return False
        try:
            return bool(self.player.get_status().get('playing'))
        except Exception:
            return False

    def _maybe_restart(self):
        with self._lock:
            if self.state != 'ready' or not self.pending:
                return
            if self.pending == 'idle' and self._playing():
                return              # _on_album_end will call back
            self.pending = None
        self.restart()

    def _on_album_end(self):
        # Fires on the player thread the moment the last track ends; the
        # player is idle now, so an 'idle' restart is due.
        threading.Thread(target=self._maybe_restart, daemon=True).start()

    def restart(self):
        log.info('update: relaunching into %s', self.updater.current_release())
        if self.player is not None:
            try:
                self.player.shutdown()
            except Exception:
                log.exception('player shutdown before relaunch')
        self._relaunch(self.updater.relaunch_argv(self.argv))

    def _exec_current(self, argv):
        env = dict(os.environ, **self.updater.env())
        sys.stdout.flush()
        sys.stderr.flush()
        # cwd would otherwise stay the old release folder, which gets pruned.
        os.chdir(self.updater.current_link)
        os.execve(argv[0], argv, env)

    # --- periodic ----------------------------------------------------------

    def start(self):
        """Begin the periodic check (and, with auto on, the install-when-idle)
        loop. No-op on an unmanaged install."""
        if not self.managed or self._loop_thread is not None:
            return
        self._loop_thread = threading.Thread(target=self._loop, name='lp-update', daemon=True)
        self._loop_thread.start()

    _loop_thread = None

    def stop(self):
        self._stop.set()

    def _loop(self):
        # First check shortly after boot, then every check_hours.
        delay = 60
        while not self._stop.wait(delay):
            delay = self.check_hours * 3600
            self.check()
            if self.auto and self.updater.available() and self.state == 'idle':
                self.install('idle')


# --- command line --------------------------------------------------------------

def _cmd_status(u, _args):
    print(f'home:     {u.home}')
    print(f'current:  {u.current_release() or "(none)"}')
    print(f'managed:  {u.is_managed()}')
    return 0


def _cmd_check(u, _args):
    latest = u.check()
    current = u.current_release()
    print(f'installed: {current or "(none)"}')
    print(f'latest:    {latest["tag"]}  ({latest["title"]}, {latest["published_at"]})')
    print('update available' if u.available() else 'up to date')
    return 0


def _cmd_install(u, args):
    def show():
        p = u.progress
        if p.get('total'):
            pct = p['done'] * 100 // p['total']
            print(f'\r  {p["phase"]} {p["asset"]}: {pct}%   ', end='', flush=True)
        else:
            print(f'\r  {p.get("phase", "")} {p.get("asset", "")}   ', end='', flush=True)

    ticker = threading.Event()

    def tick():
        while not ticker.wait(0.2):
            show()

    threading.Thread(target=tick, daemon=True).start()
    try:
        tag = u.install(force=args.force)
    finally:
        ticker.set()
        print()
    print(f'installed {tag}; current -> releases/{tag}')
    if args.restart:
        _restart_unit()
    return 0


def _restart_unit():
    """Restart the systemd user unit if there is one; the app's own relaunch
    covers the case where the CLI is run from inside a running app's box."""
    ctl = shutil.which('systemctl')
    if ctl:
        subprocess.run([ctl, '--user', 'restart', UNIT_NAME], check=False)


def _cmd_bootstrap(u, args):
    """First install: venv from the system python, then a normal install."""
    os.makedirs(u.home, exist_ok=True)
    u.ensure_venv()
    return _cmd_install(u, args)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--home', default=None, help='install root (default: $LP_HOME or ~/lp)')
    ap.add_argument('--repo', default=GITHUB_REPO, help='GitHub owner/name to update from')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status').set_defaults(fn=_cmd_status)
    sub.add_parser('check').set_defaults(fn=_cmd_check)
    for name, fn in (('install', _cmd_install), ('bootstrap', _cmd_bootstrap)):
        p = sub.add_parser(name)
        p.add_argument('--force', action='store_true', help='reinstall the current release')
        p.add_argument('--restart', action='store_true', help='restart the lp user service after')
        p.set_defaults(fn=fn)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    u = Updater(args.home, repo=args.repo)
    try:
        return args.fn(u, args)
    except UpdateError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f'error: {" ".join(e.cmd)} exited {e.returncode}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
