"""QueuePlayer — track-level queue on top of lpcore.PlayerBackend (req #3).

lpcore's PlayerBackend is album-oriented (play_album → builds a VLC MediaList
from a directory's files). lp-deck needs an arbitrary queue of tracks, so this
wraps it and manages queue order, current index, and prev/next.

NOTE: a clean implementation needs a small lpcore addition —
`PlayerBackend.play_tracks(files, album_path=None)` (generalise play_album to an
explicit file list). Until then the transport methods are stubs that hold the
queue model so the UI can be built against the final shape.
"""


class QueuePlayer:
    def __init__(self, backend, scrobbler=None):
        self.backend = backend          # lpcore.player.PlayerBackend
        self.scrobbler = scrobbler       # lpcore.scrobbler.Scrobbler
        self.queue = []                  # list of track dicts (path, title, …)
        self.index = -1

    def set_queue(self, tracks, start=0):
        self.queue = list(tracks)
        self.index = start if self.queue else -1
        self._play_current()

    def enqueue(self, track):
        self.queue.append(track)

    def _play_current(self):
        if not (0 <= self.index < len(self.queue)):
            return
        # TODO: backend.play_tracks([t['path'] for t in self.queue], start=self.index)
        # For now, fall back to album playback of the current track's album.
        track = self.queue[self.index]
        album_dir = track.get("album_path")
        if album_dir:
            self.backend.play_album(album_dir)

    def next(self):
        if self.index + 1 < len(self.queue):
            self.index += 1
            self._play_current()

    def previous(self):
        if self.index > 0:
            self.index -= 1
            self._play_current()

    def toggle(self):
        # TODO: backend pause/resume; stop for now
        status = self.backend.get_status()
        if status.get("playing"):
            self.backend.stop()
        else:
            self._play_current()

    def shutdown(self):
        self.backend.shutdown()
