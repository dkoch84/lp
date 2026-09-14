"""Build the assets a release ships: the source tarball, the rendered vinyl
caches, and a manifest that ties them together.

The release workflow (.github/workflows/release.yml) runs this on a tag push
and attaches the output to the GitHub Release; ``lp.update`` on a kiosk reads
the manifest back to decide what to download. Nothing here needs the app's
dependencies: git and the standard library only, so it also works from a bare
checkout.

    python -m lp.release --tag crucible-and-ruin --out dist/

Assets written to ``--out``:

    lp-<tag>.tar.gz                the checkout at that tag (git archive) plus
                                   a RELEASE file naming the tag, so a tarball
                                   install reports its release without git
    vinyl-cache-<family>.tar.gz    one per cache family (mandelbrot, nebula,
                                   munafo): the PNGs under lpcore/cache/<family>
    release-manifest.json          sha256 + size of every asset above, and the
                                   sha256 of every cached image per family, so
                                   an updater downloads a family only when one
                                   of its images actually changed

The images are committed to git (they are what was looked at), so this packs
them straight from the checkout. Families are separate so a retuned nebula
style costs a kiosk the nebula tarball, not the whole 150 MB cache.
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile

from lpcore.paths import repo_dir
from lpcore.version import RELEASE_TITLES

CACHE_FAMILIES = ('mandelbrot', 'nebula', 'munafo')
MANIFEST_NAME = 'release-manifest.json'


def source_asset_name(tag):
    return f'lp-{tag}.tar.gz'


def cache_asset_name(family):
    return f'vinyl-cache-{family}.tar.gz'


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def build_source_tarball(tag, out_path, repo=None):
    """``git archive`` of ``tag`` with a RELEASE stamp appended.

    The archive is taken uncompressed so the stamp can be appended with
    tarfile, then gzipped in one pass; ``git archive`` itself cannot add a file
    that is not in the tree.
    """
    repo = repo or repo_dir()
    prefix = f'lp-{tag}/'
    raw = subprocess.run(['git', '-C', repo, 'archive', '--format=tar',
                          f'--prefix={prefix}', tag],
                         capture_output=True, check=True).stdout
    with open(out_path, 'wb') as out, tarfile.open(fileobj=out, mode='w:gz') as tar:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as src:
            for member in src:
                tar.addfile(member, src.extractfile(member) if member.isfile() else None)
        stamp = tag.encode() + b'\n'
        info = tarfile.TarInfo(prefix + 'RELEASE')
        info.size = len(stamp)
        tar.addfile(info, io.BytesIO(stamp))


def build_cache_tarball(family, cache_root, out_path):
    """Pack ``<cache_root>/<family>/*.png`` as ``<family>/<name>.png``.

    Returns {name: sha256} for the manifest, or None when the family folder has
    no images (a family the build machine never rendered is simply absent
    from the release rather than shipped empty).
    """
    folder = os.path.join(cache_root, family)
    names = sorted(n for n in os.listdir(folder)) if os.path.isdir(folder) else []
    names = [n for n in names if n.endswith('.png') and not n.startswith('.')]
    if not names:
        return None
    hashes = {}
    with tarfile.open(out_path, 'w:gz', compresslevel=1) as tar:   # PNGs don't shrink
        for name in names:
            path = os.path.join(folder, name)
            tar.add(path, arcname=f'{family}/{name}')
            hashes[name] = sha256_file(path)
    return hashes


def build(tag, out_dir, cache_root=None, repo=None, families=CACHE_FAMILIES, log=print):
    """Build every asset into ``out_dir`` and return the manifest dict."""
    repo = repo or repo_dir()
    cache_root = cache_root or os.path.join(repo, 'lpcore', 'cache')
    os.makedirs(out_dir, exist_ok=True)

    manifest = {
        'release': tag,
        'title': RELEASE_TITLES.get(tag, tag),
        'source': source_asset_name(tag),
        'assets': {},
        'cache': {},
    }

    src_name = source_asset_name(tag)
    log(f'  {src_name}')
    build_source_tarball(tag, os.path.join(out_dir, src_name), repo)

    for family in families:
        name = cache_asset_name(family)
        hashes = build_cache_tarball(family, cache_root, os.path.join(out_dir, name))
        if hashes is None:
            log(f'  {name}: no images under {cache_root}/{family}, skipped')
            continue
        log(f'  {name}: {len(hashes)} images')
        manifest['cache'][family] = {'asset': name, 'files': hashes}

    for name in [src_name] + [c['asset'] for c in manifest['cache'].values()]:
        path = os.path.join(out_dir, name)
        manifest['assets'][name] = {'sha256': sha256_file(path), 'size': os.path.getsize(path)}

    with open(os.path.join(out_dir, MANIFEST_NAME), 'w') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    log(f'  {MANIFEST_NAME}')
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--tag', required=True, help='the release tag to package (must exist)')
    ap.add_argument('--out', default='dist', help='output folder (default: dist/)')
    ap.add_argument('--cache', default=None,
                    help='cache root to pack (default: lpcore/cache in the checkout)')
    args = ap.parse_args(argv)
    try:
        build(args.tag, args.out, cache_root=args.cache)
    except subprocess.CalledProcessError as e:
        print(f'git archive failed: {e.stderr.decode(errors="replace").strip()}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
