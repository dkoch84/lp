import os
import re
from dataclasses import dataclass, field

from lpcore.covers import find_cover
from lpcore.tracks import (AUDIO_EXTENSIONS, album_track_names, album_track_paths,  # noqa: F401
                           is_audio, natural_key)

YEAR_RE = re.compile(r'^(\d{4})\s*[-–—]\s*(.+)$')


def parse_album_folder(folder_name):
    """(year, display name) for an album folder: "1996 - Title" gives
    ("1996", "Title"); a folder without a leading year gives ("", folder)."""
    m = YEAR_RE.match(folder_name)
    if m:
        return m.group(1), m.group(2).strip()
    return '', folder_name


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

                try:
                    entries = os.listdir(album_path)
                except OSError:
                    continue
                track_names = sorted((f for f in entries if is_audio(f)), key=natural_key)
                track_count = len(track_names)
                if track_count == 0:
                    continue

                year, display_name = self._parse_folder_name(album_folder)
                cover_path = find_cover(
                    album_path, [os.path.join(album_path, n) for n in track_names[:2]],
                    names=entries)

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

            # Always present an artist's albums chronologically. Albums with no
            # parseable year sort last, then alphabetically.
            artist.albums.sort(
                key=lambda al: (al.year == '', al.year, al.display_name.lower()))

            if artist.albums:
                artists[artist_name] = artist

        self.artists = artists
        self.albums_by_path = albums_by_path
        print(f"Library: {len(self.artists)} artists, {len(self.albums_by_path)} albums")

    def _parse_folder_name(self, folder_name):
        return parse_album_folder(folder_name)

    def _find_cover(self, album_path):
        return find_cover(album_path, album_track_paths(album_path)[:2])

    def get_artists(self):
        return sorted(self.artists.values(), key=lambda a: a.name.lower())

    def get_artist(self, name):
        return self.artists.get(name)

    def get_album_by_path(self, path):
        return self.albums_by_path.get(path)

    def get_album_tracks(self, album_path):
        return album_track_names(album_path)
