"""Reading and writing playlist files: M3U / M3U8, PLS and XSPF.

Entries are dicts: ``path`` (absolute, always present), and ``title``,
``artist`` and ``duration`` (seconds) where the file says. Relative entries are
resolved against the playlist's own folder, and ``file://`` URLs are decoded.
Web streams (http:// and the like) are skipped: lp-deck plays local files.
"""
import os
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

FORMATS = {'.m3u': 'm3u', '.m3u8': 'm3u', '.pls': 'pls', '.xspf': 'xspf'}
_XSPF_NS = 'http://xspf.org/ns/0/'


def format_for(path):
    """'m3u', 'pls' or 'xspf' from a file name, or None."""
    return FORMATS.get(os.path.splitext(path)[1].lower())


def _local_path(location, base_dir):
    """An absolute local path for a playlist entry, or None for a stream."""
    location = location.strip()
    if not location:
        return None
    if '://' in location:
        url = urlparse(location)
        if url.scheme != 'file':
            return None
        location = unquote(url.path)
    location = location.replace('\\', '/') if os.sep == '/' and '\\' in location and ':' not in location else location
    if not os.path.isabs(location):
        location = os.path.join(base_dir, location)
    return os.path.normpath(location)


def _read_text(path):
    with open(path, 'rb') as f:
        raw = f.read()
    for encoding in ('utf-8-sig', 'latin-1'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def _parse_extinf(line):
    """(duration, artist, title) from '#EXTINF:123,Artist - Title'."""
    info = line[len('#EXTINF:'):]
    seconds, _, name = info.partition(',')
    try:
        duration = float(seconds.split()[0]) if seconds.strip() else None
    except ValueError:
        duration = None
    if duration is not None and duration < 0:
        duration = None
    artist, sep, title = name.partition(' - ')
    if not sep:
        artist, title = '', name
    return duration, artist.strip() or None, title.strip() or None


def _read_m3u(path):
    base = os.path.dirname(os.path.abspath(path))
    entries, pending = [], {}
    for line in _read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith('#EXTINF:'):
            duration, artist, title = _parse_extinf(line)
            pending = {'duration': duration, 'artist': artist, 'title': title}
            continue
        if line.startswith('#'):
            continue
        local = _local_path(line, base)
        if local:
            entries.append({'path': local, **{k: v for k, v in pending.items() if v is not None}})
        pending = {}
    return entries


def _read_pls(path):
    base = os.path.dirname(os.path.abspath(path))
    fields = {}
    for line in _read_text(path).splitlines():
        key, sep, value = line.strip().partition('=')
        if not sep:
            continue
        key = key.strip().lower()
        for name in ('file', 'title', 'length'):
            if key.startswith(name) and key[len(name):].isdigit():
                fields.setdefault(int(key[len(name):]), {})[name] = value.strip()
    entries = []
    for number in sorted(fields):
        f = fields[number]
        local = _local_path(f.get('file', ''), base)
        if not local:
            continue
        entry = {'path': local}
        if f.get('title'):
            entry['title'] = f['title']
        try:
            length = float(f.get('length', ''))
            if length >= 0:
                entry['duration'] = length
        except ValueError:
            pass
        entries.append(entry)
    return entries


def _read_xspf(path):
    base = os.path.dirname(os.path.abspath(path))
    root = ET.parse(path).getroot()

    def child(el, name):
        found = el.find(f'{{{_XSPF_NS}}}{name}')
        if found is None:
            found = el.find(name)
        return found.text if found is not None and found.text else None

    tracks = root.findall(f'.//{{{_XSPF_NS}}}track') or root.findall('.//track')
    entries = []
    for track in tracks:
        local = _local_path(child(track, 'location') or '', base)
        if not local:
            continue
        entry = {'path': local}
        if child(track, 'title'):
            entry['title'] = child(track, 'title')
        if child(track, 'creator'):
            entry['artist'] = child(track, 'creator')
        try:
            entry['duration'] = int(child(track, 'duration')) / 1000.0
        except (TypeError, ValueError):
            pass
        entries.append(entry)
    return entries


def read_playlist(path):
    """Entries from a playlist file. Raises ValueError for an unknown type."""
    fmt = format_for(path)
    if fmt == 'm3u':
        return _read_m3u(path)
    if fmt == 'pls':
        return _read_pls(path)
    if fmt == 'xspf':
        return _read_xspf(path)
    raise ValueError(f"not a playlist file lp-deck reads (m3u, m3u8, pls, xspf): {path}")


def write_playlist(path, tracks):
    """Write `tracks` (dicts with path, and optionally title, artist, duration)
    as the playlist type named by `path`'s extension. Paths are written as
    absolute paths (file URLs in XSPF). Raises ValueError for an unknown type."""
    fmt = format_for(path)
    tracks = [t for t in tracks if t.get('path')]
    if fmt == 'm3u':
        lines = ['#EXTM3U']
        for t in tracks:
            name = ' - '.join(x for x in (t.get('artist'), t.get('title')) if x)
            lines.append(f"#EXTINF:{int(round(t.get('duration') or -1))},{name}")
            lines.append(t['path'])
        text = '\n'.join(lines) + '\n'
    elif fmt == 'pls':
        lines = ['[playlist]']
        for i, t in enumerate(tracks, start=1):
            lines.append(f"File{i}={t['path']}")
            if t.get('title'):
                lines.append(f"Title{i}={t['title']}")
            lines.append(f"Length{i}={int(round(t.get('duration') or -1))}")
        lines += [f"NumberOfEntries={len(tracks)}", 'Version=2']
        text = '\n'.join(lines) + '\n'
    elif fmt == 'xspf':
        ET.register_namespace('', _XSPF_NS)
        root = ET.Element(f'{{{_XSPF_NS}}}playlist', version='1')
        track_list = ET.SubElement(root, f'{{{_XSPF_NS}}}trackList')
        for t in tracks:
            el = ET.SubElement(track_list, f'{{{_XSPF_NS}}}track')
            ET.SubElement(el, f'{{{_XSPF_NS}}}location').text = \
                'file://' + '/'.join(_quote_part(p) for p in os.path.abspath(t['path']).split('/'))
            if t.get('title'):
                ET.SubElement(el, f'{{{_XSPF_NS}}}title').text = t['title']
            if t.get('artist'):
                ET.SubElement(el, f'{{{_XSPF_NS}}}creator').text = t['artist']
            if t.get('duration'):
                ET.SubElement(el, f'{{{_XSPF_NS}}}duration').text = str(int(t['duration'] * 1000))
        text = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode') + '\n'
    else:
        raise ValueError(f"unknown playlist type (use .m3u, .m3u8, .pls or .xspf): {path}")
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def _quote_part(part):
    from urllib.parse import quote
    return quote(part)
