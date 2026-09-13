"""QueuePlayer — a play queue over lpcore.PlayerBackend (req #3).

The backend loads the whole track list and advances through it gaplessly (the lp
"magic"), so this is a thin wrapper: set_queue loads the list, and prev/next/
pause delegate to the backend's list player. `queue` keeps the display rows
(track dicts) parallel to what's loaded; the backend owns the play position.

Adds the table-stakes transport extras on top of the gapless core: shuffle,
repeat, add-to-queue / play-next, volume, seeking, and save/restore of the
session so a relaunch resumes where you left off.
"""
import json
import logging
import os
import random

log = logging.getLogger("lpdeck.player")


def _durations(tracks):
    """Lengths the library already knows, so the backend needn't open each file."""
    return [float(t.get("duration") or 0) for t in tracks]


def drop_missing(tracks, index, offset, exists=os.path.exists):
    """Leave out tracks whose files are gone (moved, deleted, share not mounted)
    from a saved session, so the queue doesn't stall on them. Keeps the index on
    the same track, or on the next one that exists if it was the current track
    that went missing (from its start). Returns (tracks, index, offset, dropped)."""
    present = [(i, t) for i, t in enumerate(tracks) if t.get("path") and exists(t["path"])]
    if len(present) == len(tracks):
        return list(tracks), index, offset, 0
    kept = [t for _, t in present]
    before = sum(1 for i, _ in present if i < index)
    current_kept = any(i == index for i, _ in present)
    new_index = min(before, max(len(kept) - 1, 0))
    return kept, new_index, (offset if current_kept else 0.0), len(tracks) - len(kept)


class QueuePlayer:
    def __init__(self, backend, scrobbler=None):
        self.backend = backend          # lpcore.player.PlayerBackend
        self.scrobbler = scrobbler       # lpcore.scrobbler.Scrobbler
        self.queue = []                  # list of track dicts (path, title, …)
        self.album_path = None           # album context of the current queue
        self.shuffle = False
        self.repeat = "off"              # off | all | one
        self._natural = []               # queue order before shuffling
        self._autosave_path = None

    def set_queue(self, tracks, start=0, album_path=None):
        """Replace the queue with `tracks` (dicts incl. 'path') and start playing
        at index `start`. Honours the current shuffle setting (the chosen start
        track stays first)."""
        tracks = list(tracks)
        self._natural = list(tracks)
        self.album_path = album_path
        if not tracks:
            self.queue = []
            return
        if self.shuffle:
            head = tracks[start] if 0 <= start < len(tracks) else tracks[0]
            rest = [t for i, t in enumerate(tracks) if i != start]
            random.shuffle(rest)
            tracks = [head] + rest
            start = 0
        self.queue = tracks
        self.backend.play_tracks([t["path"] for t in self.queue],
                                 album_path=album_path, start=start,
                                 durations=_durations(self.queue))

    def restore_queue(self, tracks, start, offset, album_path=None):
        """Reload a saved session paused at `offset` seconds into track `start`."""
        tracks = list(tracks)
        self._natural = list(tracks)
        self.queue = tracks
        self.album_path = album_path
        if not tracks:
            return
        start = max(0, min(start, len(tracks) - 1))
        self.backend.play_tracks([t["path"] for t in tracks], album_path=album_path,
                                 start=start, paused=True, start_offset=offset,
                                 durations=_durations(tracks))

    def add_tracks(self, tracks, play_next=False):
        """Append (or insert-next) tracks onto the current queue without
        interrupting playback. Starts a fresh queue if nothing is playing."""
        tracks = list(tracks)
        if not tracks:
            return
        if not self.queue:
            self.set_queue(tracks, start=0)
            return
        paths = [t["path"] for t in tracks]
        if play_next:
            cur = self.current()
            at = self.index + 1
            self.queue[at:at] = tracks
            # Keep the unshuffled order in step too, or turning shuffle off would
            # restore an order that doesn't contain these tracks.
            n = next((i for i, t in enumerate(self._natural) if t is cur), None)
            pos = len(self._natural) if n is None else n + 1
            self._natural[pos:pos] = tracks
            self.backend.insert_tracks_next(paths, durations=_durations(tracks))
        else:
            self.queue.extend(tracks)
            self._natural.extend(tracks)
            self.backend.append_tracks(paths, durations=_durations(tracks))

    def set_shuffle(self, on):
        """Toggle shuffle for the tracks still to come. The playing track and the
        ones already played stay where they are, so playback carries on without a
        break: shuffling reorders what's next, and turning it off puts what's next
        back in the order it was queued."""
        on = bool(on)
        if on == self.shuffle:
            return
        self.shuffle = on
        if not self.queue:
            return
        cut = self.index + 1
        upcoming = list(self.queue[cut:])
        if on:
            random.shuffle(upcoming)
        else:
            still_to_come = {id(t) for t in upcoming}
            upcoming = [t for t in self._natural if id(t) in still_to_come]
        self.queue = self.queue[:cut] + upcoming
        self.backend.replace_upcoming([t["path"] for t in upcoming],
                                      durations=_durations(upcoming))

    def set_repeat(self, mode):
        self.repeat = mode if mode in ("off", "all", "one") else "off"
        self.backend.set_repeat(self.repeat)

    def cycle_repeat(self):
        self.set_repeat({"off": "all", "all": "one", "one": "off"}[self.repeat])
        return self.repeat

    def jump_to(self, index):
        """Play the queued track at `index` (no-op if out of range). The backend
        moves within the loaded list, so the queue isn't reloaded."""
        if 0 <= index < len(self.queue):
            self.backend.jump_to(index)

    def remove(self, index):
        """Take the track at `index` out of the queue."""
        if not 0 <= index < len(self.queue):
            return
        gone = self.queue.pop(index)
        self._natural = [t for t in self._natural if t is not gone]
        if not self.queue:
            self.album_path = None
        self.backend.remove_track(index)

    def move(self, src, dst):
        """Move the track at `src` to position `dst`."""
        n = len(self.queue)
        if not (0 <= src < n and 0 <= dst < n) or src == dst:
            return
        self.queue.insert(dst, self.queue.pop(src))
        if not self.shuffle:
            self._natural = list(self.queue)   # the unshuffled order is the one you arranged
        self.backend.move_track(src, dst)

    def clear(self):
        """Stop and empty the queue."""
        self.queue = []
        self._natural = []
        self.album_path = None
        self.backend.clear_queue()

    @property
    def stop_after_current(self):
        return bool(getattr(self.backend, "stop_after_current", False))

    def set_stop_after_current(self, on):
        """Pause when the playing track ends, ready at the start of the next."""
        self.backend.stop_after_current = bool(on)

    def seek_by(self, seconds):
        """Move `seconds` forward (or back, if negative) in the playing track;
        going past its end moves to the next track."""
        target = self.backend.get_current_time() + seconds
        length = self.backend.get_total_time()
        if length and target >= length:
            self.backend.next_track()
            return
        self.backend.seek_track(max(0.0, target))

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

    # --- volume / seek passthrough ---

    def set_volume(self, vol):
        self.backend.set_volume(vol)

    def get_volume(self):
        return self.backend.get_volume()

    def toggle_mute(self):
        self.backend.toggle_mute()

    def seek(self, frac):
        self.backend.seek_fraction(frac)

    # --- session persistence (resume on launch) ---

    def save_state(self, path=None):
        """Write the session (queue, position, shuffle, repeat) to `path`, or to
        the autosave path. Written to a temporary file and renamed, so a crash
        mid-write can't leave a truncated session behind."""
        path = path or self._autosave_path
        if not path:
            return
        try:
            state = {
                "queue": list(self.queue),
                "index": self.index,
                "offset": self.backend.get_current_time(),
                "album_path": self.album_path,
                "shuffle": self.shuffle,
                "repeat": self.repeat,
            }
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            tmp = f"{path}.tmp"
            with open(tmp, "w") as f:
                json.dump(state, f)
            os.replace(tmp, path)
        except Exception as e:               # saving must never break playback
            log.warning("could not save the session to %s: %s", path, e)

    def enable_autosave(self, path):
        """Save the session whenever playback starts, stops, the track changes or
        the queue is edited, not only on a clean exit, so a crash or a killed
        process resumes close to where it was."""
        self._autosave_path = path
        for event in ("play_start", "track_change", "stop", "queue_change"):
            self.backend.on(event, self.save_state)

    def shutdown(self):
        self.backend.shutdown()
