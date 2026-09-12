import vlc
import os
import glob
import logging
import threading
import time
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3


AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.aac', '.ogg', '.oga',
                    '.opus', '.wav', '.wma', '.aiff', '.aif')
log = logging.getLogger("lp.player")


class PlayerBackend:
    def __init__(self, audio_output='alsa', replaygain='none'):
        self._audio_output = audio_output
        # --no-audio-time-stretch: lp never changes playback rate, and VLC's
        # time-stretch otherwise swallows the first frames of the next track at a
        # gapless boundary (audible as a clipped first word on direct ALSA).
        args = [f'--aout={audio_output}', '--no-audio-time-stretch']
        # ReplayGain (volume normalisation) reads the files' RG tags. Instance-
        # level in libVLC, so a mode change needs a reload (PlayerBackend rebuild
        # or play_tracks re-issue) — handled at the app level.
        self._replaygain = replaygain if replaygain in ('track', 'album') else 'none'
        if self._replaygain != 'none':
            args.append(f'--audio-replay-gain-mode={self._replaygain}')
        self._instance = vlc.Instance(*args)
        # MediaListPlayer drives a MediaList for gapless playback: it preloads
        # the next item and switches without tearing down the audio output, so
        # albums with continuous audio across a track boundary (e.g. a reverb
        # tail or ambient bed flowing from one track into the next) play without
        # the dropout a per-track set_media()/play() reload would introduce.
        self._list_player = self._instance.media_list_player_new()
        self.player = self._instance.media_player_new()
        self._list_player.set_media_player(self.player)
        self._media_list = None
        # MRL of each track in album order; used to resolve the authoritative
        # current index from the player on each NextItemSet event.
        self._mrls = []
        self._lock = threading.Lock()
        self._callbacks = {}
        self._playing = False

        # Vinyl display config (style, label, brightness, label text/decor) now
        # lives in lpcore.vinyl.VinylSettings, owned at the app level — the
        # player is just audio playback.
        self.album_path = None
        self.album = []
        self.current_song_index = 0
        self.track_durations = []
        self.track_boundaries = []
        self.album_duration = 0.0
        # monotonic time the current track's stream ended — paired with the next
        # advance to measure the audible gap at the boundary (gapless diagnostics).
        self._last_end_t = None
        # True while swapping the media list — suppresses stale list events from
        # the outgoing playback so they don't desync state on the new queue.
        self._loading = False

        # --- equalizer (live, runtime-settable) ---
        self._eq = None

        # --- crossfade engine (opt-in; 0 = pure gapless list player) ---
        # When crossfade is on we can't use the single gapless list player (it
        # has no overlap), so playback routes through a manual two-player engine:
        # the next track starts on the idle player and the two volumes ramp past
        # each other. self.player stays player A; _player_b is player B.
        self._xf_ms = 0
        self._player_b = None
        self._xf_idx = 0                 # 0 → self.player active, 1 → _player_b
        self._xf_master_vol = 100
        self._xf_fading = False
        self._xf_stop = threading.Event()
        self._xf_thread = None
        self._repeat_mode = 'off'        # honoured by the crossfade monitor

        self._attach_events()

    def _attach_events(self):
        em = self._list_player.event_manager()
        if em:
            em.event_attach(vlc.EventType.MediaListPlayerNextItemSet, self._on_next_item)
            em.event_attach(vlc.EventType.MediaListPlayerPlayed, self._on_list_end)
        pem = self.player.event_manager()
        if pem:
            pem.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_track_end)

    def _on_track_end(self, event):
        self._last_end_t = time.monotonic()
        with self._lock:
            idx = self.current_song_index
        log.info("track %d ended (stream)", idx + 1)

    def _on_next_item(self, event):
        # Fired once per item as the list player advances (including the first
        # item at play start). Resolve the index from the player's current
        # media rather than counting, so a missed/duplicate event can't desync.
        fire = None
        with self._lock:
            if not self._playing or self._loading:
                return
            media = self.player.get_media()
            if media is None:
                return
            try:
                idx = self._mrls.index(media.get_mrl())
            except ValueError:
                return
            if idx == self.current_song_index:
                return  # initial item — already reflected by play_start
            self.current_song_index = idx
            fire = 'track_change'
            total = len(self.album)
            title = os.path.basename(self.album[idx]) if idx < len(self.album) else '?'
        if fire:
            # gap = wall-clock between the old track ending and the new one being
            # set. ~0 (or negative, preloaded) = gapless; large positive = a gap.
            gap = (time.monotonic() - self._last_end_t) * 1000.0 if self._last_end_t else None
            log.info("advance -> track %d/%d (%s)%s", idx + 1, total, title,
                     f"  boundary gap {gap:+.0f}ms" if gap is not None else "")
            self._fire(fire)

    def _on_list_end(self, event):
        with self._lock:
            if self._loading:
                return
            self._playing = False
        log.info("album end")
        self._fire('album_end')

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
        self.play_tracks(files, album_path=album_path)

    def play_tracks(self, files, album_path=None, start=0, paused=False,
                    start_offset=0.0):
        """Play an explicit list of track paths gaplessly (a queue), starting at
        index ``start``. ``album_path`` is optional context (used for vinyl style
        selection + logging). play_album() is just this over a directory listing.
        ``paused``/``start_offset`` restore a saved session: load the queue, jump
        to ``start_offset`` seconds into the start track, and pause immediately.
        """
        files = list(files)
        if not files:
            return
        if self._xf_ms > 0:
            return self._play_crossfade(files, album_path, start, paused, start_offset)

        durations = [self._get_file_duration(f) for f in files]
        boundaries, cumulative = [], 0.0
        for dur in durations:
            boundaries.append(cumulative)
            cumulative += dur

        media_list = self._instance.media_list_new()
        mrls = []
        for f in files:
            m = self._instance.media_new(f)
            media_list.add_media(m)
            mrls.append(m.get_mrl())

        # Stop any in-flight playback BEFORE swapping the list. A VLC
        # MediaListPlayer that's already playing won't switch to a freshly-set
        # media list — it keeps playing the old item (so every "Play" looked
        # like a no-op and the now-playing index desynced). `_loading` muffles
        # the stale stop/advance events during the swap.
        with self._lock:
            self._loading = True
        self._list_player.stop()

        with self._lock:
            self.album_path = album_path
            self.album = files
            self.current_song_index = max(0, min(start, len(files) - 1))
            self.track_durations = durations
            self.track_boundaries = boundaries
            self.album_duration = cumulative
            self._playing = True
            self._media_list = media_list
            self._mrls = mrls
            self._last_end_t = None
            self._loading = False
            start_idx = self.current_song_index

        ctx = os.path.basename(album_path.rstrip('/')) if album_path else f"{len(files)} tracks"
        log.info("play: %s — %d tracks, %.0fs, start=%d, aout=%s",
                 ctx, len(files), cumulative, start_idx, self._audio_output)
        self._list_player.set_media_list(media_list)
        if start_idx:
            self._list_player.play_item_at_index(start_idx)
        else:
            self._list_player.play()
        if start_offset > 0:
            threading.Timer(0.2, self.player.set_time,
                            (int(start_offset * 1000),)).start()
        if paused:
            threading.Timer(0.3, self.player.set_pause, (1,)).start()
        self._fire('play_start')

    def stop(self):
        self._stop_xf_thread()
        with self._lock:
            self._playing = False
        self._list_player.stop()
        if self._player_b is not None:
            try:
                self._player_b.stop()
            except Exception:
                pass
        self._fire('stop')

    def next_track(self):
        """Skip to the next item in the loaded list (no-op past the end)."""
        if self._xf_ms > 0 and self._playing:
            with self._lock:
                nxt = self.current_song_index + 1
                n = len(self.album)
            if nxt >= n:
                nxt = 0 if self._repeat_mode == 'all' else None
            if nxt is not None:
                self._xf_jump(nxt)
            return
        self._list_player.next()

    def prev_track(self):
        if self._xf_ms > 0 and self._playing:
            with self._lock:
                prv = max(0, self.current_song_index - 1)
            self._xf_jump(prv)
            return
        self._list_player.previous()

    def toggle_pause(self):
        """Pause/resume the current track (VLC pause toggles)."""
        if self._xf_ms > 0:
            self._active().pause()
            if self._xf_fading and self._player_b is not None:
                self._idle().pause()
            return
        self._list_player.pause()

    def set_repeat(self, mode):
        """Repeat mode: 'off' | 'all' (loop the queue) | 'one' (repeat track)."""
        self._repeat_mode = mode if mode in ('off', 'all', 'one') else 'off'
        m = {'off': vlc.PlaybackMode.default,
             'all': vlc.PlaybackMode.loop,
             'one': vlc.PlaybackMode.repeat}.get(mode, vlc.PlaybackMode.default)
        self._list_player.set_playback_mode(m)

    def set_paused(self, paused):
        """Explicit pause (True) / resume (False) — for MPRIS Play/Pause, which
        are distinct verbs unlike the toggle the transport button uses."""
        if self._xf_ms > 0:
            self._active().set_pause(1 if paused else 0)
            return
        self.player.set_pause(1 if paused else 0)

    def is_actively_playing(self):
        """True only while audio is actually advancing (False when paused). The
        `_playing` flag means 'has a loaded queue', which stays True over a pause."""
        try:
            return bool(self._active().is_playing())
        except Exception:
            return False

    # --- volume (0–100) ---

    def set_volume(self, vol):
        v = max(0, min(100, int(vol)))
        self._xf_master_vol = v
        try:
            self._active().audio_set_volume(v)
        except Exception:
            pass

    def get_volume(self):
        return self._xf_master_vol

    def toggle_mute(self):
        self._active().audio_toggle_mute()

    def set_mute(self, on):
        self._active().audio_set_mute(bool(on))

    def is_muted(self):
        return bool(self._active().audio_get_mute())

    # --- seeking (album-wide: the seek bar spans the whole queue) ---

    def seek_fraction(self, frac):
        """Seek to `frac` (0–1) of the *whole queue* duration, crossing track
        boundaries if needed. Within the current track it sets time directly;
        across tracks it jumps to the target item then applies the offset once
        the new media is playing (VLC ignores set_time before the item starts)."""
        with self._lock:
            if not self._playing or self.album_duration <= 0:
                return
            target = max(0.0, min(1.0, frac)) * self.album_duration
            idx = 0
            for i, b in enumerate(self.track_boundaries):
                if b <= target:
                    idx = i
                else:
                    break
            offset_ms = int((target - self.track_boundaries[idx]) * 1000)
            cur = self.current_song_index
        if self._xf_ms > 0:
            if idx == cur:
                self._active().set_time(offset_ms)
            else:
                self._xf_jump(idx)
                if offset_ms > 0:
                    threading.Timer(0.15, self._active().set_time,
                                    (offset_ms,)).start()
            return
        if idx == cur:
            self.player.set_time(offset_ms)
        else:
            self._list_player.play_item_at_index(idx)
            if offset_ms > 0:
                threading.Timer(0.15, self.player.set_time, (offset_ms,)).start()

    def seek_track(self, seconds):
        """Set the position within the *current track* (MPRIS SetPosition)."""
        self._active().set_time(max(0, int(seconds * 1000)))

    # --- equalizer (live, runtime-settable) ---

    @staticmethod
    def eq_bands():
        """Centre frequencies (Hz) of the equalizer bands (10 in libVLC)."""
        out = []
        try:
            n = vlc.libvlc_audio_equalizer_get_band_count()
            for i in range(n):
                out.append(vlc.libvlc_audio_equalizer_get_band_frequency(i))
        except Exception:
            pass
        return out

    def set_equalizer(self, enabled, preamp=0.0, bands=None):
        """Apply (or clear) a live equalizer. `bands` is a list of per-band dB
        gains (len == eq_bands()); `preamp` is dB.

        NB: this python-vlc build segfaults on ``AudioEqualizer(preset_index)``
        (the new-from-preset ctype is mistracked), so we ALWAYS build an empty
        equalizer and set the amps ourselves — preset *curves* live in the app
        layer and arrive here as explicit band lists."""
        if not enabled:
            self._eq = None
            try:
                self.player.set_equalizer(None)
                if self._player_b is not None:
                    self._player_b.set_equalizer(None)
            except Exception:
                pass
            return
        try:
            eq = vlc.AudioEqualizer()          # empty — never the preset ctor
            eq.set_preamp(float(preamp))
            for i, amp in enumerate(bands or []):
                eq.set_amp_at_index(float(amp), i)
            self._eq = eq
            self.player.set_equalizer(eq)
            if self._player_b is not None:
                self._player_b.set_equalizer(eq)
        except Exception as e:
            log.warning("equalizer failed: %s", e)

    # --- crossfade engine (two-player overlap; only when _xf_ms > 0) ---

    def set_crossfade(self, ms):
        """Set the crossfade length in ms (0 = pure gapless list player). Takes
        effect immediately: the current queue is re-issued through the matching
        engine at the current track + position."""
        ms = max(0, int(ms))
        if ms == self._xf_ms:
            return
        with self._lock:
            files = list(self.album)
            idx = self.current_song_index
            ap = self.album_path
            playing = self._playing
        offset = self.get_current_time()
        self._stop_xf_thread()
        self._xf_ms = ms
        if playing and files:
            try:
                self._list_player.stop()
            except Exception:
                pass
            if self._player_b is not None:
                try:
                    self._player_b.stop()
                except Exception:
                    pass
            self.play_tracks(files, album_path=ap, start=idx, start_offset=offset)

    def _ensure_player_b(self):
        if self._player_b is None:
            self._player_b = self._instance.media_player_new()
            if self._eq is not None:
                try:
                    self._player_b.set_equalizer(self._eq)
                except Exception:
                    pass
        return self._player_b

    def _active(self):
        return self.player if self._xf_idx == 0 else self._player_b

    def _idle(self):
        return self._player_b if self._xf_idx == 0 else self.player

    def _start_xf_thread(self):
        self._xf_stop.clear()
        self._xf_thread = threading.Thread(target=self._xf_monitor, daemon=True)
        self._xf_thread.start()

    def _stop_xf_thread(self):
        self._xf_stop.set()
        t = self._xf_thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.0)
        self._xf_thread = None

    def _play_crossfade(self, files, album_path, start, paused, start_offset):
        self._ensure_player_b()
        self._stop_xf_thread()
        durations = [self._get_file_duration(f) for f in files]
        boundaries, cum = [], 0.0
        for d in durations:
            boundaries.append(cum)
            cum += d
        with self._lock:
            self._loading = True
        self._list_player.stop()              # release the output from gapless mode
        try:
            self._player_b.stop()
        except Exception:
            pass
        with self._lock:
            self.album_path = album_path
            self.album = files
            self.current_song_index = max(0, min(start, len(files) - 1))
            self.track_durations = durations
            self.track_boundaries = boundaries
            self.album_duration = cum
            self._playing = True
            self._xf_idx = 0
            self._xf_fading = False
            self._loading = False
            start_idx = self.current_song_index
        act = self.player
        m = self._instance.media_new(files[start_idx])
        act.set_media(m)
        act.audio_set_volume(self._xf_master_vol)
        act.play()
        if start_offset > 0:
            threading.Timer(0.2, act.set_time, (int(start_offset * 1000),)).start()
        if paused:
            threading.Timer(0.3, act.set_pause, (1,)).start()
        log.info("play (crossfade %dms): %d tracks, start=%d, aout=%s",
                 self._xf_ms, len(files), start_idx, self._audio_output)
        self._start_xf_thread()
        self._fire('play_start')

    def _next_index(self, idx, n):
        if idx + 1 < n:
            return idx + 1
        return 0 if self._repeat_mode == 'all' else None

    def _xf_monitor(self):
        """Poll the active player; when it nears the end, overlap the next track
        and ramp the two volumes past each other."""
        while not self._xf_stop.wait(0.2):
            with self._lock:
                if not self._playing or self._xf_fading:
                    continue
                idx = self.current_song_index
                n = len(self.album)
            act = self._active()
            try:
                state = act.get_state()
                length = act.get_length()
                t = act.get_time()
            except Exception:
                continue
            if state == vlc.State.Ended:
                if self._repeat_mode == 'one':
                    self._restart_current()
                    continue
                nxt = self._next_index(idx, n)
                if nxt is None:
                    with self._lock:
                        self._playing = False
                    self._fire('album_end')
                    return
                self._hard_advance(nxt)
                continue
            if length <= 0 or t < 0 or self._repeat_mode == 'one':
                continue
            if (length - t) <= self._xf_ms:
                nxt = self._next_index(idx, n)
                if nxt is not None and nxt != idx:
                    self._do_crossfade(nxt)

    def _do_crossfade(self, nxt):
        with self._lock:
            if self._xf_fading:
                return
            self._xf_fading = True
            files = list(self.album)
            master = self._xf_master_vol
        cur, other = self._active(), self._idle()
        try:
            other.set_media(self._instance.media_new(files[nxt]))
            other.audio_set_volume(0)
            other.play()
        except Exception:
            with self._lock:
                self._xf_fading = False
            return
        dur = self._xf_ms / 1000.0
        steps = max(1, int(dur / 0.05))
        for s in range(1, steps + 1):
            if self._xf_stop.is_set():
                break
            p = s / steps
            try:
                cur.audio_set_volume(int(master * (1 - p)))
                other.audio_set_volume(int(master * p))
            except Exception:
                pass
            time.sleep(dur / steps)
        try:
            cur.stop()
            other.audio_set_volume(master)
        except Exception:
            pass
        with self._lock:
            self._xf_idx ^= 1
            self.current_song_index = nxt
            self._xf_fading = False
        self._fire('track_change')

    def _hard_advance(self, nxt):
        """Load `nxt` on the active player without a fade (used at a natural end
        the crossfade didn't pre-trigger, e.g. repeat-all wrap)."""
        act = self._active()
        try:
            act.set_media(self._instance.media_new(self.album[nxt]))
            act.audio_set_volume(self._xf_master_vol)
            act.play()
        except Exception:
            return
        with self._lock:
            self.current_song_index = nxt
        self._fire('track_change')

    def _restart_current(self):
        try:
            self._active().set_time(0)
            self._active().play()
        except Exception:
            pass

    def _xf_jump(self, idx):
        """Hard-jump to track `idx` on the active player (manual next/prev/seek)."""
        with self._lock:
            self._xf_fading = True            # freeze the monitor over the swap
            n = len(self.album)
        if self._player_b is not None:
            try:
                self._idle().stop()
            except Exception:
                pass
        act = self._active()
        try:
            act.set_media(self._instance.media_new(self.album[idx]))
            act.audio_set_volume(self._xf_master_vol)
            act.play()
        except Exception:
            pass
        with self._lock:
            self.current_song_index = max(0, min(idx, n - 1))
            self._xf_fading = False
        self._fire('track_change')

    # --- live queue edits (no playback interruption) ---

    def append_tracks(self, files):
        """Append tracks to the live media list without restarting playback
        (VLC MediaList is live; the list player keeps going)."""
        return self._add_tracks(files, at=None)

    def insert_tracks_next(self, files):
        """Insert tracks right after the current one (play-next)."""
        return self._add_tracks(files, at=self.current_song_index + 1)

    def _add_tracks(self, files, at):
        files = [f for f in files if f]
        if not files or self._media_list is None:
            return
        with self._lock:
            ml = self._media_list
            for off, f in enumerate(files):
                m = self._instance.media_new(f)
                if at is None:
                    ml.add_media(m)
                    self.album.append(f)
                    self._mrls.append(m.get_mrl())
                else:
                    pos = at + off
                    ml.insert_media(m, pos)
                    self.album.insert(pos, f)
                    self._mrls.insert(pos, m.get_mrl())
            # recompute durations / boundaries / total for the new list
            self.track_durations = [self._get_file_duration(p) for p in self.album]
            self.track_boundaries, cum = [], 0.0
            for d in self.track_durations:
                self.track_boundaries.append(cum)
                cum += d
            self.album_duration = cum
        self._fire('track_change')

    def _get_file_duration(self, file_path):
        try:
            lower = file_path.lower()
            if lower.endswith('.mp3'):
                return MP3(file_path).info.length
            elif lower.endswith('.flac'):
                return FLAC(file_path).info.length
            from mutagen import File as MutagenFile
            mf = MutagenFile(file_path)
            if mf is not None and mf.info is not None:
                return float(getattr(mf.info, 'length', 0.0) or 0.0)
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
        self._list_player.release()
        self.player.release()
        if self._player_b is not None:
            try:
                self._player_b.release()
            except Exception:
                pass
