import json
import os
import threading
import time


# How many recently-played albums the "Recently Played" section keeps.
RECENT_ALBUMS_LIMIT = 8


class UserState:
    """Persists per-user library state: favorited artists, last-played times,
    and the most recently played albums.

    Stored as JSON; safe to read/write from multiple threads.
    """

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self.favorites = set()
        self.last_played = {}
        self.grid_covers = {}  # artist -> ordered list of album folder names
        # Most-recent-first list of {"artist", "folder", "ts"}; capped at
        # RECENT_ALBUMS_LIMIT, deduped by (artist, folder).
        self.recent_albums = []
        self._load()

    def _load(self):
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path) as f:
                data = json.load(f)
            self.favorites = set(data.get('favorites', []))
            self.last_played = {
                k: float(v) for k, v in data.get('last_played', {}).items()
            }
            self.grid_covers = {
                k: list(v) for k, v in data.get('grid_covers', {}).items()
            }
            self.recent_albums = [
                {'artist': e['artist'], 'folder': e['folder'],
                 'ts': float(e.get('ts', 0))}
                for e in data.get('recent_albums', [])
                if e.get('artist') and e.get('folder')
            ][:RECENT_ALBUMS_LIMIT]
        except Exception as e:
            print(f"Failed to load user state: {e}")

    def _save_locked(self):
        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump({
                    'favorites': sorted(self.favorites),
                    'last_played': self.last_played,
                    'grid_covers': self.grid_covers,
                    'recent_albums': self.recent_albums,
                }, f, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            print(f"Failed to save user state: {e}")

    def is_favorite(self, artist):
        with self._lock:
            return artist in self.favorites

    def set_favorite(self, artist, value):
        with self._lock:
            if value:
                self.favorites.add(artist)
            else:
                self.favorites.discard(artist)
            self._save_locked()

    def get_grid_covers(self, artist):
        with self._lock:
            return list(self.grid_covers.get(artist, []))

    def set_grid_covers(self, artist, folders):
        with self._lock:
            if folders:
                self.grid_covers[artist] = list(folders)
            else:
                self.grid_covers.pop(artist, None)  # empty → revert to default
            self._save_locked()

    def mark_played(self, artist):
        with self._lock:
            self.last_played[artist] = time.time()
            self._save_locked()

    def get_last_played(self, artist):
        with self._lock:
            return self.last_played.get(artist)

    def mark_album_played(self, artist, folder):
        """Record an album play at the front of the recently-played list.

        Re-playing an album moves it back to the top rather than duplicating
        it, and the list is capped at RECENT_ALBUMS_LIMIT.
        """
        if not artist or not folder:
            return
        with self._lock:
            self.recent_albums = [
                e for e in self.recent_albums
                if not (e['artist'] == artist and e['folder'] == folder)
            ]
            self.recent_albums.insert(
                0, {'artist': artist, 'folder': folder, 'ts': time.time()})
            del self.recent_albums[RECENT_ALBUMS_LIMIT:]
            self._save_locked()

    def get_recent_albums(self):
        """Most-recent-first copy of the recently-played albums."""
        with self._lock:
            return [dict(e) for e in self.recent_albums]
