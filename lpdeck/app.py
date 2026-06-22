"""lp-deck main window.

Left nav (Artists / Playlists / Queue) + search, a central stacked view (the
library browser is live; Playlists/Queue are stubs), and a now-playing bar with
the spinning VinylWidget driven by lpcore player events.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                               QListWidget, QStackedWidget, QLineEdit, QLabel,
                               QPushButton, QComboBox)

from lpcore.vinyl.settings import VinylSettings
from . import db
from .library_view import LibraryView
from .vinyl_widget import VinylWidget

NAV = ["Artists", "Playlists", "Queue"]


class MainWindow(QMainWindow):
    # emitted (possibly from a VLC/worker thread) → marshalled to the UI thread
    _np_changed = Signal()
    library_indexed = Signal()

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

        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 6)
        body.setSpacing(12)
        outer.addLayout(body, 1)

        # left nav + search
        left = QVBoxLayout()
        left.setSpacing(8)
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

        # central stacked views — library is live, rest stubbed
        self.stack = QStackedWidget()
        self.library = LibraryView(con, self._play)
        self.stack.addWidget(self.library)
        self.stack.addWidget(self._placeholder("Playlists"))
        self.stack.addWidget(self._placeholder("Queue"))
        body.addWidget(self.stack, 1)

        outer.addWidget(self._now_playing_bar())

        # player events → now-playing (queued across the VLC thread boundary)
        self._np_changed.connect(self._update_now_playing)
        for ev in ("play_start", "track_change", "stop"):
            self.player.backend.on(ev, self._np_changed.emit)
        self.library_indexed.connect(self.library.refresh)

    def _placeholder(self, name):
        w = QLabel(f"{name} view — TODO")
        w.setAlignment(Qt.AlignCenter)
        return w

    def _now_playing_bar(self):
        bar = QWidget()
        bar.setObjectName("nowPlaying")
        bar.setFixedHeight(108)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(14)

        self.vinyl = VinylWidget(VinylSettings())
        self.vinyl.setFixedSize(88, 88)
        lay.addWidget(self.vinyl)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.np_title = QLabel("—")
        self.np_title.setObjectName("npTitle")
        self.np_sub = QLabel("")
        self.np_sub.setObjectName("npSub")
        info.addStretch(1)
        info.addWidget(self.np_title)
        info.addWidget(self.np_sub)
        info.addStretch(1)
        lay.addLayout(info, 1)

        for label, slot, name in (("⏮", self._prev, None),
                                   ("⏵", self._toggle, "playButton"),
                                   ("⏭", self._next, None)):
            b = QPushButton(label)
            if name:
                b.setObjectName(name)
            else:
                b.setFixedWidth(40)
            b.clicked.connect(slot)
            lay.addWidget(b)

        self.scope = QComboBox()
        self.scope.addItems(["Vinyl: Global", "Vinyl: Artist", "Vinyl: Album"])
        lay.addWidget(self.scope)
        return bar

    # --- playback ---

    def _play(self, tracks, start, album_path):
        self.player.set_queue(tracks, start=start, album_path=album_path)

    def _prev(self):
        self.player.previous()

    def _next(self):
        self.player.next()

    def _toggle(self):
        self.player.toggle()

    def _update_now_playing(self):
        st = self.player.backend.get_status()
        if not st.get("playing"):
            self.np_title.setText("—")
            self.np_sub.setText("")
            self.vinyl.set_spinning(False)
            return
        self.np_title.setText(st.get("track_title") or "")
        self.np_sub.setText(" — ".join(x for x in (st.get("artist"), st.get("album")) if x))

        backend = self.player.backend
        album_path = backend.album_path
        if album_path:
            self.vinyl.set_settings(self._resolve_vinyl(album_path))
            self.vinyl.set_album(album_path, list(backend.track_boundaries),
                                 backend.album_duration, backend.find_album_art(album_path),
                                 st.get("artist"), st.get("album"))
        self.vinyl.set_spinning(True)

    def _resolve_vinyl(self, album_path):
        """Per-album → per-artist → global vinyl override (req #7)."""
        row = self.con.execute("SELECT id, artist_id FROM albums WHERE path=?",
                               (album_path,)).fetchone()
        if row:
            d = db.resolve_vinyl_settings(self.con, album_id=row["id"],
                                          artist_id=row["artist_id"])
        else:
            d = db.resolve_vinyl_settings(self.con)
        return VinylSettings.from_dict(d)
