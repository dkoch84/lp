"""Render the vinyl style images the renderer loads from lpcore/cache/.

A mandelbrot or nebula style with no cached image is rendered live every time
it is drawn, which is fine for most styles (under a second) and far too slow
for layered smoke like teal-marble (tens of seconds, on whatever thread asked).
The cached images are committed, so a checkout has them; render after adding
or retuning a style, and commit the result:

    make prerender                  # styles that are missing or out of date
    make prerender ONLY=teal-marble # one style, whether cached or not
    make prerender FORCE=1          # every style again (slow)
    python -m lpcore.vinyl.prerender --check   # exit 1 if any is stale (CI)

"Out of date" is decided per style, not per file: every rendered image is
recorded in ``<family>/.keys.json`` with a key derived from the style's
parameter tuple and the source of the renderer code that tuple reaches (the
render entry point and every module function or constant it references,
transitively). Retune teal-marble's parameters and only teal-marble renders
again; touch the smoke renderer itself and the nebula family does. This is
what lets the release workflow verify, in seconds, that the committed images
match the committed code, instead of rendering anything itself.

Munafo images come from fractals.prerender_all() and are committed to git.
"""
import argparse
import hashlib
import inspect
import json
import os
import sys
import time
import types

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from lpcore.vinyl.cache import CACHE_DIR, NEBULA_CACHE_DIR
from lpcore.vinyl.catalog import MANDELBROT_VARIANTS, PRERENDER_SIZE
from lpcore.vinyl.fractals import NEBULA_VARIANTS, _render_mandelbrot_surface, _render_nebula_surface

KEYS_FILE = '.keys.json'

# Module globals a renderer reads that do not change its output (in-process
# cache sizing), so editing them must not invalidate every image.
_FINGERPRINT_IGNORE = {'_FIELD_CACHE_BYTES', '_FIELD_CACHE_LIMIT'}


def _jobs():
    for v in MANDELBROT_VARIANTS:
        yield f"{v[4]}-{v[5]}", os.path.join(CACHE_DIR, f"{v[4]}-{v[5]}.png"), _render_mandelbrot_surface, v
    for v in NEBULA_VARIANTS:
        yield v[2], os.path.join(NEBULA_CACHE_DIR, f"{v[2]}.png"), _render_nebula_surface, v


# --- style keys --------------------------------------------------------------------

def _source(fn):
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return repr(fn)


def _stable(value):
    """A repr of a variant tuple that is stable across runs: functions by their
    source (a palette function IS a parameter), dicts in sorted order."""
    if isinstance(value, types.FunctionType):
        return f'<fn {value.__name__}>{_source(value)}'
    if isinstance(value, dict):
        return '{' + ','.join(f'{k!r}:{_stable(v)}' for k, v in sorted(value.items(), key=repr)) + '}'
    if isinstance(value, (list, tuple)):
        return '(' + ','.join(_stable(v) for v in value) + ')'
    return repr(value)


def renderer_fingerprint(fn, _seen=None):
    """The source of ``fn`` and, transitively, of every function in its module
    that it references by name, plus the repr of every module-level constant
    it references. Any edit to that code changes the fingerprint."""
    seen = _seen if _seen is not None else set()
    module = sys.modules.get(fn.__module__)
    parts = [_source(fn)]
    for name in getattr(fn, '__code__', None) and fn.__code__.co_names or ():
        if name in seen or name in _FINGERPRINT_IGNORE or module is None:
            continue
        obj = module.__dict__.get(name)
        if isinstance(obj, types.FunctionType) and obj.__module__ == fn.__module__:
            seen.add(name)
            parts.append(renderer_fingerprint(obj, seen))
        elif isinstance(obj, (dict, list, tuple, str, int, float)):
            seen.add(name)
            parts.append(f'{name}={_stable(obj)}')
    return ''.join(parts)


def style_key(render, variant, size=PRERENDER_SIZE):
    """What a cached image was rendered from; equal keys mean an identical image."""
    text = f'{size}|{_stable(variant)}|{renderer_fingerprint(render)}'
    return hashlib.sha256(text.encode()).hexdigest()


def _keys_path(image_path):
    return os.path.join(os.path.dirname(image_path), KEYS_FILE)


def load_keys(folder):
    try:
        with open(os.path.join(folder, KEYS_FILE)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _record_key(image_path, name, key):
    folder = os.path.dirname(image_path)
    keys = load_keys(folder)
    keys[name] = key
    tmp = os.path.join(folder, KEYS_FILE + '.part')
    with open(tmp, 'w') as f:
        json.dump(keys, f, indent=1, sort_keys=True)
    os.replace(tmp, os.path.join(folder, KEYS_FILE))


def plan():
    """(name, path, render, variant, key, reason) for every style; reason is
    'new', 'changed' or None when the cached image is current."""
    keys_by_folder = {}
    for name, path, render, variant in _jobs():
        folder = os.path.dirname(path)
        if folder not in keys_by_folder:
            keys_by_folder[folder] = load_keys(folder)
        key = style_key(render, variant)
        if not os.path.isfile(path):
            reason = 'new'
        elif keys_by_folder[folder].get(name) != key:
            reason = 'changed'
        else:
            reason = None
        yield name, path, render, variant, key, reason


def _save(surf, path):
    """Write next to the target, then rename, so a running app never loads a
    half-written image."""
    folder, name = os.path.split(path)
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, f".{name[:-4]}.part.png")
    pygame.image.save(surf, tmp)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", action="append", default=[],
                    help="style name to render (repeatable), cached or not")
    ap.add_argument("--force", action="store_true", help="render every style again")
    ap.add_argument("--check", action="store_true",
                    help="render nothing; exit 1 listing styles that are missing or out of date")
    args = ap.parse_args(argv)

    if args.check:
        stale = [(name, reason) for name, _p, _r, _v, _k, reason in plan() if reason]
        for name, reason in stale:
            print(f"  {name}: {reason}")
        print(f"{len(stale)} style image(s) need rendering (run make prerender and commit)"
              if stale else "every style image is current")
        return 1 if stale else 0

    pygame.init()
    known = {name for name, *_ in _jobs()}
    unknown = [n for n in args.only if n not in known]
    if unknown:
        print(f"unknown style(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    done = 0
    for name, path, render, variant, key, reason in plan():
        if args.only:
            if name not in args.only:
                continue
            reason = 'requested'
        elif args.force:
            reason = 'forced'
        elif reason is None:
            continue
        print(f"  rendering {name} ({reason}) at {PRERENDER_SIZE}px radius...", end=" ", flush=True)
        started = time.monotonic()
        _save(render(variant, PRERENDER_SIZE), path)
        _record_key(path, name, key)
        print(f"{time.monotonic() - started:.1f}s")
        done += 1
    print(f"rendered {done} style image(s)" if done else "every style already has a current cached image")
    return 0


if __name__ == "__main__":
    sys.exit(main())
