"""Library browser: Artists | Albums | Songs (req #1).

Three columns fed from the SQLite index. Selecting an artist filters albums;
selecting an album lists its songs; activating a song (double-click / Enter)
plays the album from that track via the on_play callback.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                               QListWidgetItem, QLabel, QSplitter)


class LibraryView(QWidget):
    def __init__(self, con, on_play, parent=None):
        super().__init__(parent)
        self.con = con
        self.on_play = on_play          # (tracks: list[dict], start: int, album_path)
        self._tracks = []               # current album's song rows (track dicts)
        self._album_path = None

        self.artists = QListWidget()
        self.albums = QListWidget()
        self.songs = QListWidget()

        split = QSplitter(self)
        for title, lst in (("ARTISTS", self.artists), ("ALBUMS", self.albums),
                           ("SONGS", self.songs)):
            col = QWidget()
            v = QVBoxLayout(col)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(4)
            header = QLabel(title)
            header.setObjectName("colHeader")
            v.addWidget(header)
            v.addWidget(lst)
            split.addWidget(col)
        split.setSizes([260, 320, 460])

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)

        self.artists.currentItemChanged.connect(self._artist_changed)
        self.albums.currentItemChanged.connect(self._album_changed)
        self.songs.itemActivated.connect(self._song_activated)

        self.refresh()

    def refresh(self):
        """(Re)load the artist column — call after (re)indexing."""
        keep = self.artists.currentRow()
        self.artists.clear()
        for r in self.con.execute("SELECT id, name FROM artists ORDER BY sort_name"):
            it = QListWidgetItem(r["name"])
            it.setData(Qt.UserRole, r["id"])
            self.artists.addItem(it)
        if self.artists.count():
            self.artists.setCurrentRow(max(0, min(keep, self.artists.count() - 1)))

    def _artist_changed(self, cur, _prev):
        self.albums.clear()
        self.songs.clear()
        if not cur:
            return
        for r in self.con.execute(
                "SELECT id, name, year, path FROM albums WHERE artist_id=? "
                "ORDER BY year, name", (cur.data(Qt.UserRole),)):
            label = f"{r['year']}  {r['name']}" if r["year"] else r["name"]
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, (r["id"], r["path"]))
            self.albums.addItem(it)
        if self.albums.count():
            self.albums.setCurrentRow(0)

    def _album_changed(self, cur, _prev):
        self.songs.clear()
        self._tracks = []
        if not cur:
            return
        album_id, self._album_path = cur.data(Qt.UserRole)
        for r in self.con.execute(
                "SELECT title, track_no, path, duration FROM tracks WHERE album_id=? "
                "ORDER BY disc_no, track_no, title", (album_id,)):
            self._tracks.append({"title": r["title"], "track_no": r["track_no"],
                                 "path": r["path"], "duration": r["duration"],
                                 "album_path": self._album_path})
            num = f"{r['track_no']:>2}.  " if r["track_no"] else ""
            it = QListWidgetItem(f"{num}{r['title']}")
            it.setData(Qt.UserRole, len(self._tracks) - 1)
            self.songs.addItem(it)

    def _song_activated(self, item):
        if self._tracks:
            self.on_play(self._tracks, item.data(Qt.UserRole), self._album_path)
