import vlc
import os
import glob
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3

class PlayerBackend:
    def __init__(self):
        self.player = vlc.MediaPlayer()
        self.player.event_manager().event_attach(vlc.EventType.MediaPlayerEndReached, self.next_song)
        self.album = []
        self.current_song_index = 0

    def play_music(self, music_files):
        if not music_files:
          print("No music files provided.")
          return
        self.album = music_files
        self.current_song_index = 0
        self.player.set_media(vlc.Media(self.album[self.current_song_index]))
        self.player.play()

    def next_song(self, event):
        if self.current_song_index + 1 < len(self.album):
            self.current_song_index += 1
            self.player.set_media(vlc.Media(self.album[self.current_song_index]))
            self.player.play()

    def get_current_song_info(self):
        if self.current_song_index < len(self.album):
            return self.find_album_art(self.album[self.current_song_index]), self.get_song_metadata(self.album[self.current_song_index])
        return None, None

    def stop_music(self):
        self.player.stop()

    def find_album_art(self, music_file_path):
        directory = os.path.dirname(music_file_path)
        patterns = ['cover.[jp][np]g', 'Cover.[jp][np]g', 'folder.[jp][np]g']
        for pattern in patterns:
            album_art_files = glob.glob(os.path.join(directory, pattern), recursive=False)
            if album_art_files:
                return album_art_files[0]
        return None

    def get_song_metadata(self, file_path):
        if file_path.lower().endswith('.mp3'):
            audio = EasyID3(file_path)
            audio_info = MP3(file_path)
        elif file_path.lower().endswith('.flac'):
            audio = FLAC(file_path)
            audio_info = FLAC(file_path)
        else:
            return None

        try:
            codec = audio_info.info.codec_name
        except AttributeError:
            codec = None

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
            'codec': codec,
            'bitrate': bitrate,
            'sampling_rate': sampling_rate,
        }

    def get_current_time(self):
        return self.player.get_time() / 1000  # get_time returns milliseconds

    def get_total_time(self):
        return self.player.get_length() / 1000  # get_length returns milliseconds