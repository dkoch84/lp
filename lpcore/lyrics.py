"""Load and parse song lyrics (LRC synced + plain/embedded unsynced).

Qt-free: stdlib + ``mutagen`` only. Used by lp players to display lyrics,
optionally synced to playback position.

Public API:
    parse_lrc(text)        -> list[(seconds, line_text)]
    load_lyrics(audio_path) -> {"synced": bool, "lines": [...], "source": str}
    active_index(lines, t)  -> int (last line with timestamp <= t, else -1)
"""
import os
import re

# A bracket group is a *timestamp* only if it looks like mm:ss(.xx). Minutes may
# exceed 59 (some LRC files do this), so don't constrain the minute width hard.
_TS_RE = re.compile(r'\[(\d+):([0-5]?\d)(?:[.:](\d{1,3}))?\]')
_OFFSET_RE = re.compile(r'\[offset:\s*([+-]?\d+)\s*\]', re.IGNORECASE)


def _ts_to_seconds(mm, ss, frac):
    secs = int(mm) * 60 + int(ss)
    if frac is not None:
        # frac is 1-3 digits of fractional seconds (centi/milli) -> scale to ms
        secs += int(frac) / (10 ** len(frac))
    return secs


def parse_lrc(text):
    """Parse LRC text into a time-sorted list of (seconds, line_text)."""
    if not text:
        return []

    # Locate an offset tag (ms to shift earlier); applied as -offset/1000.
    offset = 0.0
    m = _OFFSET_RE.search(text)
    if m:
        try:
            offset = int(m.group(1)) / 1000.0
        except ValueError:
            offset = 0.0

    entries = []  # (time, order, text) — order keeps equal-time lines stable
    order = 0
    for raw in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        # Collect leading timestamps; a line may carry several.
        stamps = []
        pos = 0
        while True:
            tm = _TS_RE.match(raw, pos)
            if not tm:
                break
            stamps.append(_ts_to_seconds(tm.group(1), tm.group(2), tm.group(3)))
            pos = tm.end()
        if not stamps:
            # No valid timestamp -> metadata/id-tag line or junk; skip it.
            continue
        line_text = raw[pos:].strip()
        for t in stamps:
            t = t - offset
            if t < 0:
                t = 0.0
            entries.append((t, order, line_text))
            order += 1

    entries.sort(key=lambda e: (e[0], e[1]))
    return [(t, txt) for t, _, txt in entries]


def active_index(lines, t):
    """Index of the last line whose timestamp <= t. -1 if none / unsynced."""
    idx = -1
    for i, entry in enumerate(lines):
        ts = entry[0]
        if ts is None:
            return -1
        if ts <= t:
            idx = i
        else:
            break
    return idx


def _read_text_file(path):
    try:
        with open(path, 'rb') as fh:
            data = fh.read()
    except OSError:
        return None
    try:
        return data.decode('utf-8', errors='replace')
    except Exception:
        try:
            return data.decode('latin-1')
        except Exception:
            return None


def _find_sibling(audio_path, ext):
    """Return path of a sibling file with the given extension (case-insensitive
    on both basename and extension). ``ext`` includes the dot, e.g. ".lrc"."""
    base, _ = os.path.splitext(audio_path)
    exact = base + ext
    if os.path.isfile(exact):
        return exact
    directory = os.path.dirname(audio_path) or '.'
    want = os.path.basename(base).lower() + ext.lower()
    try:
        for name in os.listdir(directory):
            if name.lower() == want:
                return os.path.join(directory, name)
    except OSError:
        return None
    return None


def _unsynced_lines(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return [(None, line) for line in text.split('\n')]


def _result_from_text(text, source):
    """Turn embedded/plain lyric text into a result dict (synced if it has
    LRC timestamps, else unsynced)."""
    parsed = parse_lrc(text)
    if parsed:
        return {"synced": True, "lines": parsed, "source": source}
    return {"synced": False, "lines": _unsynced_lines(text), "source": source}


def _embedded_lyrics(audio_path):
    """Extract embedded lyric text (and any synced SYLT) from tags via mutagen.
    Returns (synced_lines_or_None, text_or_None)."""
    import mutagen

    audio = mutagen.File(audio_path)
    if audio is None:
        return None, None

    tags = getattr(audio, 'tags', None)

    # ID3 (mp3): prefer synced SYLT, then unsynced USLT.
    if tags is not None:
        getall = getattr(tags, 'getall', None)
        if callable(getall):
            try:
                sylt = getall('SYLT')
            except Exception:
                sylt = []
            for frame in sylt:
                lib = getattr(frame, 'text', None)
                # SYLT.text is a list of (text, time_ms) pairs.
                if lib:
                    synced = []
                    for item in lib:
                        try:
                            txt, ms = item
                        except (TypeError, ValueError):
                            continue
                        synced.append((ms / 1000.0, (txt or '').strip()))
                    if synced:
                        synced.sort(key=lambda x: x[0])
                        return synced, None
            try:
                uslt = getall('USLT')
            except Exception:
                uslt = []
            for frame in uslt:
                txt = getattr(frame, 'text', None)
                if txt:
                    return None, txt

    # Vorbis / FLAC, MP4, and generic key lookups.
    keys = ('LYRICS', 'UNSYNCEDLYRICS', '\xa9lyr', 'lyrics', 'unsyncedlyrics')
    if tags is not None:
        for key in keys:
            try:
                val = tags.get(key)
            except Exception:
                val = None
            if not val:
                continue
            if isinstance(val, (list, tuple)):
                val = val[0] if val else None
            if val:
                return None, str(val)

    return None, None


def load_lyrics(audio_path):
    """Resolve + load lyrics for an audio file. Never raises.

    Returns {"synced": bool, "lines": list[(float|None, str)], "source": str}.
    """
    empty = {"synced": False, "lines": [], "source": ""}
    if not audio_path:
        return empty

    # 1. Sibling .lrc file.
    try:
        lrc_path = _find_sibling(audio_path, '.lrc')
        if lrc_path:
            text = _read_text_file(lrc_path)
            if text:
                parsed = parse_lrc(text)
                if parsed:
                    return {"synced": True, "lines": parsed, "source": lrc_path}
    except Exception:
        pass

    # 2. Embedded tags.
    try:
        synced, text = _embedded_lyrics(audio_path)
        if synced:
            return {"synced": True, "lines": synced, "source": audio_path}
        if text:
            return _result_from_text(text, audio_path)
    except Exception:
        pass

    # 3. Sibling .txt file (unsynced).
    try:
        txt_path = _find_sibling(audio_path, '.txt')
        if txt_path:
            text = _read_text_file(txt_path)
            if text:
                return {"synced": False, "lines": _unsynced_lines(text),
                        "source": txt_path}
    except Exception:
        pass

    # 4. Nothing.
    return empty
