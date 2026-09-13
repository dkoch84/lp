"""Render the vinyl style images the renderer loads from lpcore/cache/.

A mandelbrot or nebula style with no cached image is rendered live every time
it is drawn, which is fine for most styles (under a second) and far too slow
for layered smoke like teal-marble (tens of seconds, on whatever thread asked).
Cached images are not in git, so render them after pulling a new or retuned
style, on each machine that shows records:

    make prerender                  # styles with no cached image yet
    make prerender ONLY=teal-marble # one style, whether cached or not
    make prerender FORCE=1          # every style again (slow)

A cached image is looked up by style name only, so after retuning a style,
render it again with ONLY=<name>. Munafo and julia images come from
fractals.prerender_all().
"""
import argparse
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from lpcore.vinyl.cache import CACHE_DIR, NEBULA_CACHE_DIR
from lpcore.vinyl.catalog import MANDELBROT_VARIANTS, PRERENDER_SIZE
from lpcore.vinyl.fractals import NEBULA_VARIANTS, _render_mandelbrot_surface, _render_nebula_surface


def _jobs():
    for v in MANDELBROT_VARIANTS:
        yield f"{v[4]}-{v[5]}", os.path.join(CACHE_DIR, f"{v[4]}-{v[5]}.png"), _render_mandelbrot_surface, v
    for v in NEBULA_VARIANTS:
        yield v[2], os.path.join(NEBULA_CACHE_DIR, f"{v[2]}.png"), _render_nebula_surface, v


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
    args = ap.parse_args(argv)

    pygame.init()
    known = {name for name, *_ in _jobs()}
    unknown = [n for n in args.only if n not in known]
    if unknown:
        print(f"unknown style(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    done = 0
    for name, path, render, variant in _jobs():
        if args.only:
            if name not in args.only:
                continue
        elif not args.force and os.path.isfile(path):
            continue
        print(f"  rendering {name} at {PRERENDER_SIZE}px radius...", end=" ", flush=True)
        started = time.monotonic()
        _save(render(variant, PRERENDER_SIZE), path)
        print(f"{time.monotonic() - started:.1f}s")
        done += 1
    print(f"rendered {done} style image(s)" if done else "every style already has a cached image")
    return 0


if __name__ == "__main__":
    sys.exit(main())
