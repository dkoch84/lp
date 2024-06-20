import sys
import argparse
import yaml
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QFileDialog, QLabel
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QSize
from player_backend import PlayerBackend

class AspectRatioPixmapLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        super().setPixmap(self._pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        if not self._pixmap.isNull():
            super().setPixmap(self._pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
          
    def minimumSizeHint(self):
        return QSize(1, 1)

class MusicPlayerUI(QWidget):
    def __init__(self, music_library_path):
        super().__init__()

        self.player_backend = PlayerBackend()
        self.music_library_path = music_library_path
        self.album_art_label = AspectRatioPixmapLabel(self)
        self.title_label = QLabel(self)
        self.artist_label = QLabel(self)
        self.album_label = QLabel(self)
        self.date_label = QLabel(self)
        self.codec_label = QLabel(self)
        self.bitrate_label = QLabel(self)
        self.sampling_rate_label = QLabel(self)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Music Player')

        play_button = QPushButton('Play')
        play_button.clicked.connect(self.open_file_and_play_music)

        stop_button = QPushButton('Stop')
        stop_button.clicked.connect(self.player_backend.stop_music)

        metadata_layout = QHBoxLayout()
        metadata_layout.addWidget(self.title_label)
        metadata_layout.addWidget(self.artist_label)
        metadata_layout.addWidget(self.album_label)
        metadata_layout.addWidget(self.date_label)
        metadata_layout.addWidget(self.codec_label)
        metadata_layout.addWidget(self.bitrate_label)
        metadata_layout.addWidget(self.sampling_rate_label)

        layout = QVBoxLayout()
        layout.addWidget(self.album_art_label, 1)
        layout.addLayout(metadata_layout, 0)
        layout.addWidget(play_button, 0)
        layout.addWidget(stop_button, 0)

        self.setLayout(layout)

    def open_file_and_play_music(self):
      file_dialog = QFileDialog.getOpenFileName(self, 'Open file', self.music_library_path)
      album_art_path, metadata = self.player_backend.play_music(file_dialog[0])
      pixmap = QPixmap(album_art_path)
      self.album_art_label.setPixmap(pixmap)
      self.title_label.setText(f"Title: {metadata['title']}")
      self.artist_label.setText(f"Artist: {metadata['artist']}")
      self.album_label.setText(f"Album: {metadata['album']}")
      # Convert bitrate to kbit/s and sampling rate to kHz before setting the text
      self.bitrate_label.setText(f"Bitrate: {metadata['bitrate'] / 1000} kbit/s")
      self.sampling_rate_label.setText(f"Sampling Rate: {metadata['sampling_rate'] / 1000} kHz")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', help='Path to the config file', required=True)
    args = parser.parse_args()

    # Read the config file
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    music_library_path = config.get('music_library_path', '/home')

    app = QApplication(sys.argv)
    window = MusicPlayerUI(music_library_path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
