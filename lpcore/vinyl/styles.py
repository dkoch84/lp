"""Vinyl styles kept as data files: ``lpcore/vinyl/styles/<kind>/<name>.json``.

lp-studio ships a style by writing one of these, instead of someone pasting a
tuple into fractals.py. fractals.py turns them into NEBULA_VARIANTS entries
(``_variants_from_files``), so everything that lists or renders styles (the web
UI, lp-deck, prerender, the release) sees them exactly like hand-written ones.

A file holds::

    {"name": "teal-marble", "family": "smoke", "order": 1, "seed": 100,
     "params": {...}, "studio": {...}}

``family`` picks how ``params`` is read: ``smoke`` (the layered-smoke renderer's
SMOKE_LAYER_PARAMS keys), ``clouds`` (cloud, sky, saturation) or ``nebula``
(the _nebula_palette arguments plus saturation, warp, arm). ``order`` keeps the
catalog order stable, which matters because an album without a chosen style
picks one by position. ``studio`` holds lp-studio's own hints (whether the
colour ramp was linked, say) and never affects a render.

This module is plain JSON handling; it does not import fractals.
"""
import json
import os
import re

STYLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'styles')
FAMILIES = ('smoke', 'clouds', 'nebula')
_NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
_REQUIRED = ('name', 'family', 'order', 'seed', 'params')


class StyleFileError(ValueError):
    pass


def _folder(kind, root):
    return os.path.join(root or STYLES_DIR, kind)


def path_for(name, kind='nebula', root=None):
    return os.path.join(_folder(kind, root), f'{name}.json')


def valid_name(name):
    """Style names are lowercase words joined by hyphens (they become ids like nebula-<name>)."""
    return bool(_NAME.match(name or ''))


def _check(entry, source):
    missing = [k for k in _REQUIRED if k not in entry]
    if missing:
        raise StyleFileError(f'{source}: missing {", ".join(missing)}')
    if entry['family'] not in FAMILIES:
        raise StyleFileError(f'{source}: unknown family {entry["family"]!r}')
    if not valid_name(entry['name']):
        raise StyleFileError(f'{source}: bad style name {entry["name"]!r}')
    if not isinstance(entry['params'], dict):
        raise StyleFileError(f'{source}: params must be an object')


def load(kind='nebula', root=None):
    """Every style file of this kind, sorted by order then name."""
    folder = _folder(kind, root)
    if not os.path.isdir(folder):
        return []
    entries = []
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith('.json') or fn.startswith('.'):
            continue
        path = os.path.join(folder, fn)
        with open(path) as f:
            try:
                entry = json.load(f)
            except ValueError as e:
                raise StyleFileError(f'{path}: {e}') from e
        _check(entry, path)
        if entry['name'] != fn[:-5]:
            raise StyleFileError(f'{path}: name {entry["name"]!r} does not match the file name')
        entries.append(entry)
    return sorted(entries, key=lambda e: (e['order'], e['name']))


def names(kind='nebula', root=None):
    return [e['name'] for e in load(kind, root)]


def next_order(kind='nebula', root=None):
    return max((e['order'] for e in load(kind, root)), default=0) + 1


def to_tuples(value):
    """JSON lists back to the tuples the renderers were written with."""
    if isinstance(value, list):
        return tuple(to_tuples(v) for v in value)
    if isinstance(value, dict):
        return {k: to_tuples(v) for k, v in value.items()}
    return value


def dumps(entry):
    """Indented JSON with short flat lists (colours, ranges) kept on one line."""
    text = json.dumps(entry, indent=2)
    return re.sub(r'\[\s*([^\[\]{}]*?)\s*\]',
                  lambda m: '[' + ', '.join(p.strip() for p in m.group(1).split(',')) + ']',
                  text) + '\n'


def write(entry, kind='nebula', root=None):
    """Write a style file atomically (a running app never reads half of one).
    Returns its path."""
    _check(entry, entry.get('name', '<unnamed>'))
    folder = _folder(kind, root)
    os.makedirs(folder, exist_ok=True)
    path = path_for(entry['name'], kind, root)
    tmp = os.path.join(folder, f'.{entry["name"]}.json.part')
    with open(tmp, 'w') as f:
        f.write(dumps(entry))
    os.replace(tmp, path)
    return path
