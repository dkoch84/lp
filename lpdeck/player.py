"""QueuePlayer — a play queue over lpcore.PlayerBackend (req #3).

The backend loads the whole track list and advances through it gaplessly (the lp
"magic"), so this is a thin wrapper: set_queue loads the list, and prev/next/
pause delegate to the backend's list player. `queue` keeps the display rows
(track dicts) parallel to what's loaded; the backend owns the play position.
"""


class QueuePlayer:
    def __init__(self, backend, scrobbler=None):
        self.backend = backend          # lpcore.player.PlayerBackend
        self.scrobbler = scrobbler       # lpcore.scrobbler.Scrobbler
        self.queue = []                  # list of track dicts (path, title, …)

    def set_queue(self, tracks, start=0, album_path=None):
        """Replace the queue with `tracks` (dicts incl. 'path') and start playing
        at index `start`."""
        self.queue = list(tracks)
        if not self.queue:
            return
        self.backend.play_tracks([t["path"] for t in self.queue],
                                 album_path=album_path, start=start)

    @property
    def index(self):
        return self.backend.current_song_index

    def current(self):
        i = self.index
        return self.queue[i] if 0 <= i < len(self.queue) else None

    def next(self):
        self.backend.next_track()

    def previous(self):
        self.backend.prev_track()

    def toggle(self):
        self.backend.toggle_pause()

    def shutdown(self):
        self.backend.shutdown()
