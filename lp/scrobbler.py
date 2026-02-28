import os
import time
import threading

try:
    import pylast
except ImportError:
    pylast = None

MIN_TRACK_LENGTH = 30
MIN_SCROBBLE_PERCENT = 0.5
MIN_SCROBBLE_SECONDS = 240


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
        self._session_key_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', '.lastfm_session'
        )

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

    def _should_scrobble(self, track):
        """Check if track meets scrobble criteria."""
        if not track or track['duration'] < MIN_TRACK_LENGTH:
            return False
        elapsed = time.time() - track.get('start_time', time.time())
        return (elapsed >= track['duration'] * MIN_SCROBBLE_PERCENT or
                elapsed >= MIN_SCROBBLE_SECONDS)

    def _do_scrobble(self, track):
        """Submit scrobble in background thread."""
        if not self.authenticated or not self.enabled:
            return

        def _submit():
            try:
                self.network.scrobble(
                    artist=track['artist'],
                    title=track['title'],
                    timestamp=int(track['start_time']),
                    album=track.get('album') or '',
                    duration=int(track['duration']),
                )
                print(f"Last.fm: scrobbled {track['artist']} - {track['title']}")
            except Exception as e:
                print(f"Last.fm: scrobble failed: {e}")

        threading.Thread(target=_submit, daemon=True).start()

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

    def _on_play_start(self):
        track = self._get_track_info()
        if not track:
            return
        with self._lock:
            track['start_time'] = time.time()
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
            track['start_time'] = time.time()
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
        }
