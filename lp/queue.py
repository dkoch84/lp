"""An album queue for the kiosk: what plays after this record ends.

lp plays albums, not tracks, so the queue is a short list of albums. Tapping a
record while another is on used to just cut it off; now the web UI asks, and
"Play next" lands here. When the player reports the album has ended, the next
queued album is put on. Stop clears the queue: pressing stop means silence,
not "skip to the one after".

Thread notes: ``album_end`` fires on libVLC's event thread, which must not be
called back into, so the next album is started from a fresh thread. Everything
else is called from the API thread. One lock covers the list.
"""
import logging
import threading

log = logging.getLogger('lp.queue')

QUEUE_LIMIT = 20


class AlbumQueue:
    def __init__(self, player, library, on_play=None):
        """``on_play(album)`` is called whenever the queue starts an album by
        itself (the API uses it to note the play for Recently played)."""
        self.player = player
        self.library = library
        self.on_play = on_play
        self._paths = []
        self._lock = threading.Lock()
        if hasattr(player, 'on'):           # test stubs may not carry events
            player.on('album_end', self._on_album_end)
            player.on('stop', self.clear)

    # --- contents ---------------------------------------------------------

    def items(self):
        """Queued albums in play order, as the web UI shows them."""
        with self._lock:
            paths = list(self._paths)
        out = []
        for i, path in enumerate(paths):
            album = self.library.get_album_by_path(path)
            if album is None:
                continue
            out.append({'index': i, 'path': path, 'artist': album.artist, 'name': album.name,
                        'folder': album.folder_name,
                        'has_cover': bool(getattr(album, 'cover_path', None))})
        return out

    def summary(self):
        """What the now-playing footer needs: how many, and the first."""
        items = self.items()
        return {'count': len(items), 'next': items[0] if items else None}

    def add(self, path):
        """Queue an album, or start it right away when nothing is playing.
        Returns 'queued' or 'playing'. Raises ValueError for an unknown
        album or a full queue."""
        album = self.library.get_album_by_path(path)
        if album is None:
            raise ValueError('album path not in library')
        if not self._playing():
            self._play(album)
            return 'playing'
        with self._lock:
            if len(self._paths) >= QUEUE_LIMIT:
                raise ValueError(f'queue is full ({QUEUE_LIMIT} albums)')
            self._paths.append(path)
        log.info('queued %s', album.display_name)
        return 'queued'

    def remove(self, index):
        with self._lock:
            if not 0 <= index < len(self._paths):
                return False
            del self._paths[index]
            return True

    def clear(self):
        with self._lock:
            self._paths.clear()

    # --- playback ----------------------------------------------------------

    def _playing(self):
        try:
            return bool(self.player.get_status().get('playing'))
        except Exception:
            return False

    def _play(self, album):
        log.info('queue: playing %s', album.display_name)
        self.player.play_album(album.path)
        if self.on_play:
            self.on_play(album)

    def _on_album_end(self):
        with self._lock:
            if not self._paths:
                return
            path = self._paths.pop(0)
        album = self.library.get_album_by_path(path)
        if album is None:
            log.warning('queue: %s vanished from the library, skipping', path)
            self._on_album_end()
            return
        threading.Thread(target=self._play, args=(album,), daemon=True).start()
