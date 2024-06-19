import vlc
import os
import glob
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3

class PlayerBackend:
    def __init__(self):
        self.player = vlc.MediaPlayer()

    def play_music(self, file_path):
        if file_path:
            self.player.set_media(vlc.Media(file_path))
            self.player.play()
            return self.find_album_art(file_path), self.get_song_metadata(file_path)

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