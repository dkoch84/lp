import json
import os
import time
import threading

from lpcore.paths import data_file

try:
    import pylast
except ImportError:
    pylast = None

MIN_TRACK_LENGTH = 30
MIN_SCROBBLE_PERCENT = 0.5
MIN_SCROBBLE_SECONDS = 240
# Last.fm accepts scrobbles up to 14 days old, 50 per request.
MAX_QUEUED_AGE = 14 * 24 * 3600
BATCH = 50
MAX_QUEUED = 5000


class Scrobbler:
    def __init__(self, player, config):
        self.player = player
        self._api_key = config.get('api_key', '')
        self._api_secret = config.get('api_secret', '')
        self._configured = bool(self._api_key and self._api_secret)

        self.enabled = True
        self.username = None
        self.network = None

        self._current_track = None
        self._scrobbled = False
        self._lock = threading.Lock()

        # Session key persistence
        self._session_key_path = data_file('.lastfm_session')
        # Scrobbles that couldn't be sent (offline, Last.fm down), kept to retry.
        self._queue_path = data_file('.lastfm_queue.json')
        self._queue_lock = threading.Lock()

        self._restore_session()
        self._attach_events()

    @property
    def configured(self):
        return self._configured

    @property
    def authenticated(self):
        return self.network is not None and self.username is not None

    def _attach_events(self):
        self.player.on('play_start', self._on_play_start)
        self.player.on('track_change', self._on_track_change)
        self.player.on('album_end', self._on_album_end)
        self.player.on('stop', self._on_stop)
        # Paused time doesn't count toward the scrobble threshold. Queue edits
        # ('queue_change') are deliberately not listened to: they aren't a new
        # track, and treating them as one scrobbled the same track twice.
        self.player.on('paused', self._on_paused)
        self.player.on('resumed', self._on_resumed)

    def _restore_session(self):
        if not self._configured or not pylast:
            return
        try:
            path = os.path.normpath(self._session_key_path)
            if os.path.isfile(path):
                with open(path) as f:
                    data = f.read().strip().split('\n')
                if len(data) >= 2:
                    session_key = data[0].strip()
                    username = data[1].strip()
                    if session_key and username:
                        self.network = pylast.LastFMNetwork(
                            api_key=self._api_key,
                            api_secret=self._api_secret,
                            session_key=session_key,
                        )
                        self.username = username
                        print(f"Last.fm: restored session for {username}")
                        self._flush_in_background()
        except Exception as e:
            print(f"Last.fm: failed to restore session: {e}")

    def authenticate(self, username, password):
        if not self._configured or not pylast:
            return False, "Last.fm API key not configured"
        try:
            network = pylast.LastFMNetwork(
                api_key=self._api_key,
                api_secret=self._api_secret,
                username=username,
                password_hash=pylast.md5(password),
            )
            # Verify by getting session key
            session_key = network.session_key
            if not session_key:
                skg = pylast.SessionKeyGenerator(network)
                session_key = skg.get_session_key(username, pylast.md5(password))
                network.session_key = session_key

            self.network = network
            self.username = username

            # Persist session
            path = os.path.normpath(self._session_key_path)
            with open(path, 'w') as f:
                f.write(f"{session_key}\n{username}\n")

            print(f"Last.fm: authenticated as {username}")
            self._flush_in_background()
            return True, None
        except Exception as e:
            print(f"Last.fm: auth failed: {e}")
            return False, str(e)

    def logout(self):
        self.network = None
        self.username = None
        path = os.path.normpath(self._session_key_path)
        if os.path.isfile(path):
            os.remove(path)
        print("Last.fm: logged out")

    def _get_track_info(self):
        """Get current track metadata from player."""
        with self.player._lock:
            if not self.player.album or self.player.current_song_index >= len(self.player.album):
                return None
            path = self.player.album[self.player.current_song_index]
            duration = (self.player.track_durations[self.player.current_song_index]
                        if self.player.current_song_index < len(self.player.track_durations) else 0)
        meta = self.player.get_song_metadata(path)
        if not meta or not meta.get('artist') or not meta.get('title'):
            return None
        return {
            'artist': meta['artist'],
            'title': meta['title'],
            'album': meta.get('album'),
            'duration': duration,
        }

    @staticmethod
    def _played_seconds(track):
        """Seconds of the track actually heard: time paused is left out."""
        played = track.get('played')
        if played is None:                   # a track dict from before pause tracking
            return time.time() - track.get('start_time', time.time())
        resumed = track.get('resumed_at')
        return played + (time.monotonic() - resumed if resumed is not None else 0.0)

    @staticmethod
    def _start(track):
        track['start_time'] = time.time()    # the scrobble's timestamp
        track['played'] = 0.0
        track['resumed_at'] = time.monotonic()

    def _should_scrobble(self, track):
        """Check if track meets scrobble criteria."""
        if not track or track['duration'] < MIN_TRACK_LENGTH:
            return False
        elapsed = self._played_seconds(track)
        return (elapsed >= track['duration'] * MIN_SCROBBLE_PERCENT or
                elapsed >= MIN_SCROBBLE_SECONDS)

    def _do_scrobble(self, track):
        """Submit scrobble in background thread."""
        if not self.authenticated or not self.enabled:
            return
        threading.Thread(target=self._submit_scrobble, args=(track,), daemon=True).start()

    def _submit_scrobble(self, track):
        """Send one scrobble. If it can't be sent it goes into the queue; once one
        gets through, whatever was queued is sent too."""
        entry = {
            'artist': track['artist'],
            'title': track['title'],
            'timestamp': int(track['start_time']),
            'album': track.get('album') or '',
            'duration': int(track['duration']),
        }
        try:
            self.network.scrobble(**entry)
            print(f"Last.fm: scrobbled {track['artist']} - {track['title']}")
        except Exception as e:
            print(f"Last.fm: scrobble failed, kept to retry: {e}")
            self._enqueue(entry)
            return
        self.flush_queue()

    # --- the offline queue ---

    def _load_queue(self):
        try:
            with open(self._queue_path) as f:
                entries = json.load(f)
        except (OSError, ValueError):
            return []
        cutoff = time.time() - MAX_QUEUED_AGE
        return [e for e in entries if isinstance(e, dict) and e.get('timestamp', 0) >= cutoff]

    def _save_queue(self, entries):
        try:
            tmp = self._queue_path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(entries[-MAX_QUEUED:], f)
            os.replace(tmp, self._queue_path)
        except OSError as e:
            print(f"Last.fm: could not save the scrobble queue: {e}")

    def _enqueue(self, entry):
        with self._queue_lock:
            entries = self._load_queue()
            entries.append(entry)
            self._save_queue(entries)

    def pending_scrobbles(self):
        """How many scrobbles are waiting to be sent."""
        with self._queue_lock:
            return len(self._load_queue())

    def flush_queue(self):
        """Send queued scrobbles in batches, oldest first. Stops at the first
        failure and keeps the rest. Returns how many were sent."""
        if not self.authenticated or not self.enabled:
            return 0
        sent = 0
        with self._queue_lock:
            entries = self._load_queue()
            while entries:
                batch = entries[:BATCH]
                try:
                    self.network.scrobble_many(batch)
                except Exception as e:
                    print(f"Last.fm: queued scrobbles still can't be sent: {e}")
                    break
                entries = entries[BATCH:]
                sent += len(batch)
                self._save_queue(entries)
        if sent:
            print(f"Last.fm: sent {sent} queued scrobble(s)")
        return sent

    def _flush_in_background(self):
        threading.Thread(target=self.flush_queue, daemon=True).start()

    def _do_now_playing(self, track):
        """Send now-playing update in background thread."""
        if not self.authenticated or not self.enabled:
            return

        def _submit():
            try:
                self.network.update_now_playing(
                    artist=track['artist'],
                    title=track['title'],
                    album=track.get('album') or '',
                    duration=int(track['duration']),
                )
            except Exception as e:
                print(f"Last.fm: now-playing failed: {e}")

        threading.Thread(target=_submit, daemon=True).start()

    def _on_paused(self):
        with self._lock:
            track = self._current_track
            if track and track.get('resumed_at') is not None:
                track['played'] = track.get('played', 0.0) + time.monotonic() - track['resumed_at']
                track['resumed_at'] = None

    def _on_resumed(self):
        with self._lock:
            track = self._current_track
            if track and track.get('resumed_at') is None:
                track['resumed_at'] = time.monotonic()

    def _on_play_start(self):
        track = self._get_track_info()
        if not track:
            return
        with self._lock:
            self._start(track)
            self._current_track = track
            self._scrobbled = False
        self._do_now_playing(track)

    def _on_track_change(self):
        # Scrobble previous track
        with self._lock:
            prev = self._current_track
            was_scrobbled = self._scrobbled
        if prev and not was_scrobbled and self._should_scrobble(prev):
            self._do_scrobble(prev)

        # Start tracking new track
        track = self._get_track_info()
        if not track:
            return
        with self._lock:
            self._start(track)
            self._current_track = track
            self._scrobbled = False
        self._do_now_playing(track)

    def _on_album_end(self):
        with self._lock:
            prev = self._current_track
            was_scrobbled = self._scrobbled
            self._current_track = None
        if prev and not was_scrobbled and self._should_scrobble(prev):
            self._do_scrobble(prev)

    def _on_stop(self):
        with self._lock:
            prev = self._current_track
            was_scrobbled = self._scrobbled
            self._current_track = None
        if prev and not was_scrobbled and self._should_scrobble(prev):
            self._do_scrobble(prev)

    def get_status(self):
        return {
            'configured': self._configured,
            'authenticated': self.authenticated,
            'enabled': self.enabled,
            'username': self.username,
            'pylast_available': pylast is not None,
            'queued': self.pending_scrobbles(),
        }
