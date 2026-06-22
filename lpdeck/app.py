"""lp-deck main window (scaffold).

Layout: a left nav (Artists / Playlists / Queue) + search, a central stacked
view, and a now-playing bar with the spinning VinylWidget. Views are wired to
the SQLite index and lpcore; the view bodies are stubs to fill in next.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                               QListWidget, QStackedWidget, QLineEdit, QLabel,
                               QPushButton, QComboBox)

from lpcore.vinyl.settings import VinylSettings
from .vinyl_widget import VinylWidget

NAV = ["Artists", "Playlists", "Queue"]


class MainWindow(QMainWindow):
    def __init__(self, con, player):
        super().__init__()
        self.con = con          # sqlite connection (lpdeck.db)
        self.player = player     # lpdeck.player.QueuePlayer (wraps lpcore)
        self.setWindowTitle("lp-deck")
        self.resize(1200, 800)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)

        # --- body: nav | content ---
        body = QHBoxLayout()
        outer.addLayout(body, 1)

        # left nav + search (req #4 search, #5 filters/sorts live in each view)
        left = QVBoxLayout()
        self.search = QLineEdit(placeholderText="Search artists, albums, songs…")
        self.nav = QListWidget()
        self.nav.addItems(NAV)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(lambda i: self.stack.setCurrentIndex(i))
        left.addWidget(self.search)
        left.addWidget(self.nav, 1)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(220)
        body.addWidget(left_w)

        # central stacked views (placeholders for now)
        self.stack = QStackedWidget()
        for name in NAV:
            self.stack.addWidget(self._placeholder(name))
        body.addWidget(self.stack, 1)

        # --- now-playing bar (req #6) ---
        outer.addWidget(self._now_playing_bar())

    def _placeholder(self, name):
        w = QLabel(f"{name} view — TODO\n(wired to SQLite index + lpcore)")
        w.setAlignment(Qt.AlignCenter)
        return w

    def _now_playing_bar(self):
        bar = QWidget()
        bar.setFixedHeight(120)
        lay = QHBoxLayout(bar)

        self.vinyl = VinylWidget(VinylSettings())
        self.vinyl.setFixedSize(100, 100)
        lay.addWidget(self.vinyl)

        info = QVBoxLayout()
        self.np_title = QLabel("—")
        self.np_sub = QLabel("")
        info.addStretch(1)
        info.addWidget(self.np_title)
        info.addWidget(self.np_sub)
        info.addStretch(1)
        lay.addLayout(info, 1)

        # transport (req #3 queue control)
        for label, slot in (("⏮", self._prev), ("⏯", self._toggle), ("⏭", self._next)):
            b = QPushButton(label)
            b.setFixedWidth(44)
            b.clicked.connect(slot)
            lay.addWidget(b)

        # per-scope vinyl config selector (req #7): Global / This Artist / This Album
        self.scope = QComboBox()
        self.scope.addItems(["Vinyl: Global", "Vinyl: Artist", "Vinyl: Album"])
        lay.addWidget(self.scope)
        return bar

    # transport stubs — wired to QueuePlayer next
    def _prev(self):
        self.player.previous()

    def _next(self):
        self.player.next()

    def _toggle(self):
        self.player.toggle()
