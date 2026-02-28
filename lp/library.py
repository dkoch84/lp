import os
import re
import glob
from dataclasses import dataclass, field


AUDIO_EXTENSIONS = ('.mp3', '.flac')
COVER_PATTERNS = ['cover.[jp][np]g', 'Cover.[jp][np]g', 'folder.[jp][np]g', 'Folder.[jp][np]g']
YEAR_RE = re.compile(r'^(\d{4})\s*[-–—]\s*(.+)$')


@dataclass
class Album:
    artist: str
    name: str
    path: str
    year: str
    display_name: str
    cover_path: str
    track_count: int
    folder_name: str


@dataclass
class Artist:
    name: str
    path: str
    albums: list = field(default_factory=list)


class Library:
    def __init__(self, music_library_path):
        self.music_library_path = music_library_path
        self.artists = {}
        self.albums_by_path = {}
        self.scan()

    def scan(self):
        artists = {}
        albums_by_path = {}

        if not os.path.isdir(self.music_library_path):
            print(f"Music library path not found: {self.music_library_path}")
            self.artists = artists
            self.albums_by_path = albums_by_path
            return

        for artist_name in sorted(os.listdir(self.music_library_path)):
            artist_path = os.path.join(self.music_library_path, artist_name)
            if not os.path.isdir(artist_path):
                continue

            artist = Artist(name=artist_name, path=artist_path)

            for album_folder in sorted(os.listdir(artist_path)):
                album_path = os.path.join(artist_path, album_folder)
                if not os.path.isdir(album_path):
                    continue

                track_count = sum(
                    1 for f in os.listdir(album_path)
                    if f.lower().endswith(AUDIO_EXTENSIONS)
                )
                if track_count == 0:
                    continue

                year, display_name = self._parse_folder_name(album_folder)
                cover_path = self._find_cover(album_path)

                album = Album(
                    artist=artist_name,
                    name=album_folder,
                    path=album_path,
                    year=year,
                    display_name=display_name,
                    cover_path=cover_path,
                    track_count=track_count,
                    folder_name=album_folder,
                )
                artist.albums.append(album)
                albums_by_path[album_path] = album

            if artist.albums:
                artists[artist_name] = artist

        self.artists = artists
        self.albums_by_path = albums_by_path
        print(f"Library: {len(self.artists)} artists, {len(self.albums_by_path)} albums")

    def _parse_folder_name(self, folder_name):
        m = YEAR_RE.match(folder_name)
        if m:
            return m.group(1), m.group(2).strip()
        return '', folder_name

    def _find_cover(self, album_path):
        escaped = glob.escape(album_path)
        for pattern in COVER_PATTERNS:
            matches = glob.glob(os.path.join(escaped, pattern), recursive=False)
            if matches:
                return matches[0]
        return None

    def get_artists(self):
        return sorted(self.artists.values(), key=lambda a: a.name.lower())

    def get_artist(self, name):
        return self.artists.get(name)

    def get_album_by_path(self, path):
        return self.albums_by_path.get(path)

    def get_album_tracks(self, album_path):
        if not os.path.isdir(album_path):
            return []
        return sorted(
            f for f in os.listdir(album_path)
            if f.lower().endswith(AUDIO_EXTENSIONS)
        )
