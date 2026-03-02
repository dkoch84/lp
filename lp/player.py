import vlc
import os
import glob
import threading
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3


AUDIO_EXTENSIONS = ('.mp3', '.flac')


class PlayerBackend:
    def __init__(self):
        self._instance = vlc.Instance('--aout=alsa')
        self.player = self._instance.media_player_new()
        self._lock = threading.Lock()
        self._callbacks = {}
        self._media_ended = False
        self._playing = False

        self.vinyl_style = 'random'
        self.vinyl_label = 'art'
        self.vinyl_brightness = 100
        self.album_path = None
        self.album = []
        self.current_song_index = 0
        self.track_durations = []
        self.track_boundaries = []
        self.album_duration = 0.0

        self._attach_events()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _attach_events(self):
        em = self.player.event_manager()
        if em:
            em.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_media_end)

    def _on_media_end(self, event):
        self._media_ended = True

    def _poll_loop(self):
        while True:
            if self._media_ended:
                self._media_ended = False
                self._advance_track()
            threading.Event().wait(0.1)

    def _advance_track(self):
        event = None
        with self._lock:
            if self.current_song_index + 1 < len(self.album):
                self.current_song_index += 1
                self.player.set_media(self._instance.media_new(self.album[self.current_song_index]))
                self.player.play()
                event = 'track_change'
            else:
                self._playing = False
                event = 'album_end'
        if event:
            self._fire(event)

    def on(self, event, callback):
        self._callbacks.setdefault(event, []).append(callback)

    def _fire(self, event):
        for cb in self._callbacks.get(event, []):
            try:
                cb()
            except Exception as e:
                print(f"Callback error ({event}): {e}")

    def play_album(self, album_path):
        files = sorted(
            os.path.join(album_path, f)
            for f in os.listdir(album_path)
            if f.lower().endswith(AUDIO_EXTENSIONS)
        )
        if not files:
            print(f"No audio files in {album_path}")
            return

        durations = []
        for f in files:
            dur = self._get_file_duration(f)
            durations.append(dur)

        boundaries = []
        cumulative = 0.0
        for dur in durations:
            boundaries.append(cumulative)
            cumulative += dur

        with self._lock:
            self.album_path = album_path
            self.album = files
            self.current_song_index = 0
            self.track_durations = durations
            self.track_boundaries = boundaries
            self.album_duration = cumulative
            self._playing = True

        self.player.set_media(self._instance.media_new(files[0]))
        self.player.play()
        self._fire('play_start')

    def stop(self):
        with self._lock:
            self._playing = False
        self.player.stop()
        self._fire('stop')

    def _get_file_duration(self, file_path):
        try:
            lower = file_path.lower()
            if lower.endswith('.mp3'):
                return MP3(file_path).info.length
            elif lower.endswith('.flac'):
                return FLAC(file_path).info.length
        except Exception:
            pass
        return 0.0

    def get_current_song_info(self):
        with self._lock:
            if not self.album or self.current_song_index >= len(self.album):
                return None, None
            path = self.album[self.current_song_index]
        return self.find_album_art(path), self.get_song_metadata(path)

    def find_album_art(self, music_file_path):
        directory = os.path.dirname(music_file_path) if os.path.isfile(music_file_path) else music_file_path
        escaped = glob.escape(directory)
        patterns = ['cover.[jp][np]g', 'Cover.[jp][np]g', 'folder.[jp][np]g', 'Folder.[jp][np]g']
        for pattern in patterns:
            matches = glob.glob(os.path.join(escaped, pattern), recursive=False)
            if matches:
                return matches[0]
        return None

    def get_song_metadata(self, file_path):
        try:
            lower = file_path.lower()
            if lower.endswith('.mp3'):
                audio = EasyID3(file_path)
                audio_info = MP3(file_path)
            elif lower.endswith('.flac'):
                audio = FLAC(file_path)
                audio_info = audio
            else:
                return None

            try:
                bitrate = audio_info.info.bitrate
            except AttributeError:
                bitrate = None

            try:
                sampling_rate = audio_info.info.sample_rate
            except AttributeError:
                sampling_rate = None

            return {
                'title': audio.get('title', [None])[0],
                'artist': audio.get('artist', [None])[0],
                'album': audio.get('album', [None])[0],
                'date': audio.get('date', [None])[0],
                'bitrate': bitrate,
                'sampling_rate': sampling_rate,
            }
        except Exception:
            return None

    def get_current_time(self):
        t = self.player.get_time()
        return max(t / 1000.0, 0.0)

    def get_total_time(self):
        t = self.player.get_length()
        return max(t / 1000.0, 0.0)

    def get_album_progress(self):
        with self._lock:
            if not self._playing or not self.album:
                return {
                    'album_duration': 0.0,
                    'elapsed': 0.0,
                    'track_boundaries': [],
                }
            completed = sum(self.track_durations[:self.current_song_index])
            current_pos = self.get_current_time()
            return {
                'album_duration': self.album_duration,
                'elapsed': completed + current_pos,
                'track_boundaries': list(self.track_boundaries),
            }

    def get_status(self):
        with self._lock:
            playing = self._playing
            album_path = self.album_path
            index = self.current_song_index
            total_tracks = len(self.album)
            track_file = self.album[index] if self.album and index < len(self.album) else None

        if not playing or not track_file:
            return {
                'playing': False,
                'artist': None,
                'album': None,
                'track_title': None,
                'track_number': 0,
                'total_tracks': 0,
                'date': None,
                'progress': {
                    'album_duration': 0.0,
                    'elapsed': 0.0,
                    'track_boundaries': [],
                },
            }

        meta = self.get_song_metadata(track_file)
        progress = self.get_album_progress()

        return {
            'playing': True,
            'artist': meta.get('artist') if meta else None,
            'album': meta.get('album') if meta else None,
            'track_title': meta.get('title') if meta else None,
            'track_number': index + 1,
            'total_tracks': total_tracks,
            'date': meta.get('date') if meta else None,
            'progress': progress,
        }

    def shutdown(self):
        self.stop()
        self.player.release()
