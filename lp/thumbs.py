"""Disk-cached album-art thumbnails.

Album covers in a library are routinely 1500–3000px and 0.3–2 MB, but the web
UI shows them in ~150px tiles (and up to 4 per artist across ~200 artists). The
browsing grid was loading full-resolution originals for every tile — slow over
NFS and heavy in the browser. This downscales each cover once to a small JPEG
and caches it on disk, keyed by source path + mtime, so it regenerates
automatically if the art is replaced.

Uses pygame's image ops, which work with no display and no pygame.init() — so
this is safe to call from the API thread without touching the display's pygame.
"""
import hashlib
import io
import os
import threading
import time

import pygame

THUMB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'thumbs')
THUMB_MAX = 320  # px on the long edge — plenty for grid tiles on hi-dpi screens

_gen_lock = threading.Lock()


def _cache_path(src_path, max_size):
    """Cache file for src_path, keyed by path + mtime + size, or None if the
    source is unreadable (so a replaced cover regenerates automatically)."""
    try:
        mtime = os.stat(src_path).st_mtime_ns
    except OSError:
        return None
    key = hashlib.sha1(f'{src_path}:{mtime}:{max_size}'.encode()).hexdigest()
    return os.path.join(THUMB_DIR, key + '.jpg')


def get_thumbnail(src_path, max_size=THUMB_MAX):
    """Return JPEG bytes of a downscaled thumbnail of src_path, or None.

    Cached to disk; only cold generations are serialized (warm hits read the
    file with no lock). Concurrent cold generations of the same image are
    harmless — the write is atomic.
    """
    cache_path = _cache_path(src_path, max_size)
    if cache_path is None:
        return None

    data = _read(cache_path)
    if data is not None:
        return data

    with _gen_lock:
        data = _read(cache_path)  # another thread may have just generated it
        if data is not None:
            return data
        return _generate(src_path, cache_path, max_size)


def start_prewarm(cover_paths, initial_delay=5.0, delay=0.03, max_size=THUMB_MAX):
    """Generate any missing thumbnails in a low-priority background thread.

    Warms the cache so even the first browse is instant. Starts after
    `initial_delay` (let startup/playback settle) and sleeps `delay` between
    images so it doesn't saturate CPU/NFS on Pi-class hardware. Already-cached
    covers are skipped cheaply, so re-running after a rescan is near-free.
    """
    paths = [p for p in dict.fromkeys(cover_paths) if p]
    if not paths:
        return None

    def _run():
        time.sleep(initial_delay)
        made = 0
        for p in paths:
            cp = _cache_path(p, max_size)
            if cp is not None and not os.path.isfile(cp):
                if get_thumbnail(p, max_size) is not None:
                    made += 1
                time.sleep(delay)  # only pace cold generations
        print(f'thumbs: prewarm done — {made} generated, {len(paths)} covers',
              flush=True)

    t = threading.Thread(target=_run, daemon=True, name='thumb-prewarm')
    t.start()
    return t


def _read(path):
    try:
        with open(path, 'rb') as f:
            return f.read()
    except OSError:
        return None


def _generate(src_path, cache_path, max_size):
    try:
        img = pygame.image.load(src_path)
    except Exception:
        return None
    w, h = img.get_size()
    if w <= 0 or h <= 0:
        return None
    scale = min(max_size / float(max(w, h)), 1.0)
    if scale < 1.0:
        img = pygame.transform.smoothscale(img, (max(1, round(w * scale)),
                                                 max(1, round(h * scale))))
    buf = io.BytesIO()
    try:
        pygame.image.save(img, buf, 'JPEG')
    except Exception:
        return None
    data = buf.getvalue()

    try:
        os.makedirs(THUMB_DIR, exist_ok=True)
        tmp = cache_path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, cache_path)
    except OSError:
        pass  # serving the bytes still works even if caching failed
    return data
