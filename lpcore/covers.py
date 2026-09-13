"""Finding an album's cover: a picture file in the album folder, or art embedded
in its tracks.

Shared by the kiosk's library, the player's now-playing art and lp-deck's scan,
so every view shows the same cover. Folder pictures are matched by name without
caring about case or image type (cover, folder, front, album, albumart), then a
lone picture in the folder is taken as the cover. Albums with no picture file
fall back to the art embedded in their first tracks, extracted once into a cache
folder and reused until the track file changes.
"""
import base64
import hashlib
import os

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
# preference among several cover files of the same name
IMAGE_EXTENSIONS_ORDER = ('.jpg', '.png', '.jpeg', '.webp')
# Picture names (without extension) that mean "the cover", best first.
COVER_NAMES = ('cover', 'folder', 'front', 'album', 'albumart')


def default_cache_dir():
    """Where extracted embedded covers are kept (read at call time)."""
    base = os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache')
    return os.path.join(base, 'lp', 'covers')


def _is_image(name):
    return name.lower().endswith(IMAGE_EXTENSIONS)


def cover_file(album_dir, names=None):
    """The album folder's cover picture, or None.

    `names` is the folder listing when the caller already has it (saves a
    listdir). Preferred names win, whatever their case or image type; otherwise
    a folder holding exactly one picture uses that one.
    """
    if names is None:
        try:
            names = os.listdir(album_dir)
        except OSError:
            return None
    images = sorted(n for n in names if _is_image(n))
    if not images:
        return None
    named = [n for n in images if os.path.splitext(n)[0].lower() in COVER_NAMES]
    if named:
        # A folder can hold several covers (cover.jpg and Cover.jpg, cover.jpg
        # and cover.jpeg, Folder.jpg and cover.webp). Where the original lookup
        # found one (it knew only .jpg and .png), pick the same file so no
        # album's cover changes: .jpg/.png first, then name, then the lowercase
        # spelling, then extension.
        def rank(name):
            stem, ext = os.path.splitext(name)
            ext = ext.lower()
            return (ext not in ('.jpg', '.png'), COVER_NAMES.index(stem.lower()),
                    stem != stem.lower(), IMAGE_EXTENSIONS_ORDER.index(ext), name)
        return os.path.join(album_dir, min(named, key=rank))
    if len(images) == 1:
        return os.path.join(album_dir, images[0])
    return None


def _extension_for(mime):
    mime = (mime or '').lower()
    if 'png' in mime:
        return '.png'
    if 'webp' in mime:
        return '.webp'
    return '.jpg'


def _pictures(track_path):
    """(type, data, mime) for every picture embedded in a track."""
    pictures = []
    audio = None
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(track_path)
    except Exception:
        audio = None
    if audio is not None:
        for p in getattr(audio, 'pictures', None) or []:           # FLAC
            pictures.append((p.type, p.data, p.mime))
        tags = getattr(audio, 'tags', None)
        if tags is not None:
            getall = getattr(tags, 'getall', None)
            if callable(getall):                                     # ID3: MP3, AIFF, WAV
                for apic in getall('APIC'):
                    pictures.append((apic.type, apic.data, apic.mime))
            getter = getattr(tags, 'get', None)
            if callable(getter):
                try:
                    covr = getter('covr')                            # MP4 / M4A
                except Exception:
                    covr = None
                for c in covr or []:
                    png = getattr(c, 'imageformat', None) == 14      # MP4Cover.FORMAT_PNG
                    pictures.append((3, bytes(c), 'image/png' if png else 'image/jpeg'))
                try:
                    blocks = getter('metadata_block_picture')        # Ogg Vorbis / Opus
                except Exception:
                    blocks = None
                if blocks:
                    from mutagen.flac import Picture
                    for block in blocks:
                        try:
                            p = Picture(base64.b64decode(block))
                            pictures.append((p.type, p.data, p.mime))
                        except Exception:
                            pass
    if not pictures:
        # An ID3 tag on a file mutagen couldn't otherwise open (e.g. an MP3
        # whose audio frames it can't sync to) still carries its pictures.
        try:
            from mutagen.id3 import ID3
            for apic in ID3(track_path).getall('APIC'):
                pictures.append((apic.type, apic.data, apic.mime))
        except Exception:
            pass
    return pictures


def embedded_cover(track_path, cache_dir=None):
    """Path to a cached copy of the cover embedded in `track_path`, or None.

    Extracted once per version of the file (its path, modified time and size),
    so later calls cost a stat. A track with no art is remembered too.
    """
    cache_dir = cache_dir or default_cache_dir()
    try:
        st = os.stat(track_path)
    except OSError:
        return None
    key = hashlib.sha1(f"{track_path}\0{st.st_mtime_ns}\0{st.st_size}".encode()).hexdigest()
    for ext in ('.jpg', '.png', '.webp'):
        cached = os.path.join(cache_dir, key + ext)
        if os.path.exists(cached):
            return cached
    no_art = os.path.join(cache_dir, key + '.none')
    if os.path.exists(no_art):
        return None
    pictures = _pictures(track_path)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        if not pictures:
            open(no_art, 'w').close()
            return None
        pictures.sort(key=lambda p: 0 if p[0] == 3 else 1)          # the front cover first
        _type, data, mime = pictures[0]
        path = os.path.join(cache_dir, key + _extension_for(mime))
        tmp = path + '.part'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
        return path
    except OSError:
        return None


def find_cover(album_dir, track_paths=(), names=None, cache_dir=None):
    """An album's cover: its folder picture if it has one, otherwise art embedded
    in its first two tracks. None when there's neither."""
    found = cover_file(album_dir, names)
    if found:
        return found
    for track in list(track_paths)[:2]:
        found = embedded_cover(track, cache_dir)
        if found:
            return found
    return None
