import sys
import vlc
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QFileDialog

class MusicPlayer(QWidget):
    def __init__(self):
        super().__init__()

        self.player = vlc.MediaPlayer()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Music Player')

        play_button = QPushButton('Play')
        play_button.clicked.connect(self.play_music)

        stop_button = QPushButton('Stop')
        stop_button.clicked.connect(self.stop_music)

        layout = QVBoxLayout()
        layout.addWidget(play_button)
        layout.addWidget(stop_button)

        self.setLayout(layout)

    def play_music(self):
        file_dialog = QFileDialog.getOpenFileName(self, 'Open file', '/home')
        if file_dialog[0]:
            self.player.set_media(vlc.Media(file_dialog[0]))
            self.player.play()

    def stop_music(self):
        self.player.stop()

app = QApplication(sys.argv)
window = MusicPlayer()
window.show()
sys.exit(app.exec())