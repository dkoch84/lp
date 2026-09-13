"""QML front-end for lp-deck.

The view layer is Qt Quick (GPU scene graph — smooth scrolling/scaling, where
QWidgets icon views reflow on the CPU). Python stays the backend: a tile
image-provider renders artist/album art off-thread, ``ArtistsModel`` feeds the
grid, and ``Controller`` exposes drill-down queries + playback + now-playing
state to QML. lpcore/db/player/indexer are untouched.
"""
import os
import shutil
import subprocess
import threading
import time

from PySide6.QtCore import (Property, QAbstractListModel, QModelIndex, QObject, QSize, QUrl,
                            QSettings, Qt, QTimer, Signal, Slot)
from PySide6.QtGui import QColor, QGuiApplication, QImage, QImageReader
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickControls2 import QQuickStyle

from lpcore.vinyl.catalog import (LABEL_COLORS, MANDELBROT_VARIANTS,
                                  MUNAFO_VARIANTS, VINYL_COLORS)
from lpcore.vinyl.fractals import NEBULA_VARIANTS
from lpcore.vinyl.settings import VinylSettings
from lpcore import lyrics as lyrics_mod
from . import db, meta, mosaic, vinyl_preview
from . import indexer
from .vinyl_item import VinylItem

QML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml")

# 10-band equalizer preset curves (dB per band at 31.25…16000 Hz). libVLC's own
# new-from-preset ctor segfaults in this python-vlc build, so we ship our own.
EQ_PRESETS = {
    "Flat":        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "Rock":        [5, 4, 2, -1, -1, 1, 3, 4, 5, 5],
    "Pop":         [-1, 1, 3, 4, 4, 3, 1, -1, -1, -1],
    "Jazz":        [3, 2, 1, 2, -1, -1, 0, 1, 2, 3],
    "Classical":   [4, 3, 2, 1, -1, -1, 0, 2, 3, 4],
    "Bass Boost":  [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
    "Treble Boost": [0, 0, 0, 0, 0, 1, 3, 4, 5, 6],
    "Vocal":       [-2, -1, 1, 3, 4, 4, 3, 1, 0, -1],
}


class TileProvider(QQuickImageProvider):
    """Renders artist/album tiles on the scene-graph worker thread.

    Image id is ``artist/<id>`` or ``album/<id>``. sqlite connections aren't
    shareable across threads, so we keep one per worker thread.
    """
    def __init__(self, db_path):
        super().__init__(QQuickImageProvider.Image)
        self._db_path = db_path
        self._local = threading.local()
        self._cache_dir = os.path.join(
            os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
            "lp-deck", "tiles")
        os.makedirs(self._cache_dir, exist_ok=True)

    def _con(self):
        con = getattr(self._local, "con", None)
        if con is None:
            con = db.connect(self._db_path)
            self._local.con = con
        return con

    def requestImage(self, image_id, size, requested):
        kind, _, sid = image_id.partition("/")
        edge = requested.width() if requested.width() > 0 else 256
        try:
            sid = int(sid)
        except ValueError:
            sid = -1

        # resolve the source cover(s) — cheap DB read; the montage is the cost
        con = self._con()
        if kind == "artist":
            covers = db.artist_cover_paths(con, sid)
        else:
            row = con.execute("SELECT cover_path FROM albums WHERE id=?",
                              (sid,)).fetchone()
            covers = [row["cover_path"]] if row and row["cover_path"] else []

        # disk cache, keyed by kind/id/edge and auto-invalidated when any source
        # cover is newer than the cached tile (art added/changed since last render)
        src_mtime = max((os.path.getmtime(c) for c in covers
                         if c and os.path.exists(c)), default=0)
        cache_path = os.path.join(self._cache_dir, f"{kind}_{sid}_{edge}.png")
        if os.path.exists(cache_path) and os.path.getmtime(cache_path) >= src_mtime:
            cached = QImage(cache_path)
            if not cached.isNull():
                return cached

        if kind == "artist":
            img = mosaic.artist_image(covers, edge)
        else:
            img = mosaic.album_image(covers[0] if covers else None, edge)
        img.save(cache_path, "PNG")
        return img            # QImage; its own size is used by the scene graph


class VinylPreviewProvider(QQuickImageProvider):
    """`image://vinyl/<style>~<label>[~<album id>]` → a static disc swatch for
    the chooser.

    The album id is only added for swatches that show album art (the picture
    disc, or the album-art label), so those draw the real cover; every other
    swatch is rendered once and shared by all albums. Runs on the scene-graph
    worker threads (the chooser's images are asynchronous), so sqlite
    connections are per thread.
    """
    def __init__(self, db_path=None):
        super().__init__(QQuickImageProvider.Image)
        self._db_path = db_path
        self._local = threading.local()
        self._cache_dir = os.path.join(
            os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
            "lp-deck", "vinyl-previews")
        os.makedirs(self._cache_dir, exist_ok=True)

    def _cover(self, album_id):
        if not self._db_path or album_id < 0:
            return None
        con = getattr(self._local, "con", None)
        if con is None:
            con = db.connect(self._db_path)
            self._local.con = con
        row = con.execute("SELECT cover_path FROM albums WHERE id=?", (album_id,)).fetchone()
        path = row["cover_path"] if row else None
        return path if path and os.path.exists(path) else None

    def requestImage(self, image_id, size, requested):
        style, label, album = (image_id.split("~") + ["", ""])[:3]
        label = label or "label-white"
        edge = requested.width() if requested.width() > 0 else 160
        art = None
        if album:
            try:
                art = self._cover(int(album))
            except ValueError:
                art = None
        tag = f"_album{album}" if art else ""
        safe = f"{style}_{label}{tag}_{edge}".replace("/", "_")
        cache_path = os.path.join(self._cache_dir, safe + ".png")
        fresh = os.path.exists(cache_path) and (
            not art or os.path.getmtime(cache_path) >= os.path.getmtime(art))
        if fresh:
            cached = QImage(cache_path)
            if not cached.isNull():
                return cached
        img = vinyl_preview.preview(style, label, edge, art_path=art)
        img.save(cache_path, "PNG")
        return img


class ArtistsModel(QAbstractListModel):
    NameRole = Qt.UserRole + 1
    IdRole = Qt.UserRole + 2

    SORTS = {"name_asc": "sort_name ASC", "name_desc": "sort_name DESC"}

    def __init__(self, con, parent=None):
        super().__init__(parent)
        self.con = con
        self._rows = []
        self._filter = ""
        self._order = self.SORTS["name_asc"]
        self.reload()

    def set_sort(self, key):
        self._order = self.SORTS.get(key, self.SORTS["name_asc"])

    def reload(self):
        self.beginResetModel()
        order = self._order                       # from a fixed whitelist — safe
        if self._filter:
            self._rows = self.con.execute(
                f"SELECT id, name FROM artists WHERE name LIKE ? ORDER BY {order}",
                (f"%{self._filter}%",)).fetchall()
        else:
            self._rows = self.con.execute(
                f"SELECT id, name FROM artists ORDER BY {order}").fetchall()
        self.endResetModel()

    def set_filter(self, text):
        self._filter = text or ""
        self.reload()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        if role == self.NameRole:
            return r["name"]
        if role == self.IdRole:
            return r["id"]
        return None

    def roleNames(self):
        return {self.NameRole: b"name", self.IdRole: b"artistId"}


class QueueModel(QAbstractListModel):
    TitleRole = Qt.UserRole + 1
    ArtistRole = Qt.UserRole + 2
    DurationRole = Qt.UserRole + 3
    CurrentRole = Qt.UserRole + 4

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self._rows = []
        self._cur = -1

    def reload(self):
        """Refresh from the player. When only the playing row moved (the usual
        case: a track change), update those two rows instead of resetting the
        whole list, which would lose the view's scroll position."""
        rows = list(self.player.queue)
        cur = self.player.index
        same = (len(rows) == len(self._rows)
                and all(a is b or a.get("path") == b.get("path")
                        for a, b in zip(rows, self._rows)))
        if not same:
            self.beginResetModel()
            self._rows, self._cur = rows, cur
            self.endResetModel()
            return
        self._rows = rows
        old, self._cur = self._cur, cur
        for row in sorted({old, cur}):
            if 0 <= row < len(rows):
                i = self.index(row, 0)
                self.dataChanged.emit(i, i, [self.CurrentRole])

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role):
        if not index.isValid():
            return None
        t = self._rows[index.row()]
        if role == self.TitleRole:
            return t.get("title", "")
        if role == self.ArtistRole:
            return t.get("artist", "")
        if role == self.DurationRole:
            return t.get("duration", 0)
        if role == self.CurrentRole:
            return index.row() == self._cur
        return None

    def roleNames(self):
        return {self.TitleRole: b"title", self.ArtistRole: b"artist",
                self.DurationRole: b"duration", self.CurrentRole: b"isCurrent"}


def _mmss(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


class Controller(QObject):
    """QML-facing facade: search, drill-down queries, playback, now-playing."""
    nowPlayingChanged = Signal()
    libraryChanged = Signal()
    queueChanged = Signal()
    progressChanged = Signal()
    settingsChanged = Signal()
    playlistsChanged = Signal()
    songsChanged = Signal()
    vinylChanged = Signal()
    transportChanged = Signal()          # shuffle / repeat / volume / mute
    libraryFolderChanged = Signal()
    scanChanged = Signal()               # scanning state / status text
    _scanProgress = Signal(int, int, int)    # indexer thread → GUI thread
    _scanDone = Signal(str)
    noticeChanged = Signal()             # a short message for the user (skipped track, …)
    raiseRequested = Signal()            # bring the window forward (desktop media controls)
    externalCommand = Signal(str, str)   # requests from other threads (MPRIS), run on the GUI thread
    _backendEvent = Signal(str)          # backend thread → GUI thread
    _bump = Signal()                     # backend thread → GUI thread marshalling

    ALBUM_ORDERS = {"year": "al.year, al.name", "name": "al.name, al.year"}

    def __init__(self, con, player, artists_model, queue_model, parent=None):
        super().__init__(parent)
        self.con = con
        self.player = player
        self.artists = artists_model
        self.queue = queue_model
        self._np_title = ""
        self._np_sub = ""
        self._np_album_id = -1
        self._np_artist_id = -1
        self._np_playlist_id = -1
        self._np_accent = "#E0A24C"      # album-art-derived tint for gradients
        self._accent_cache = {}          # album_id → accent hex

        # persisted view settings (QSettings → ~/.config/lp-deck/lp-deck.conf)
        self._settings = QSettings()
        self._artist_sort = self._settings.value("artistSort", "name_asc")
        self._album_sort = self._settings.value("albumSort", "year")
        self._grid_tile = int(self._settings.value("gridTile", 152))
        self._dark = str(self._settings.value("darkMode", "true")).lower() != "false"
        self.artists.set_sort(self._artist_sort)
        self.artists.reload()

        # restore transport prefs (volume / repeat); shuffle starts off per session
        self._volume = int(self._settings.value("volume", 100))
        self.player.backend.set_volume(self._volume)
        self.player.set_repeat(str(self._settings.value("repeat", "off")))
        self._last_played_path = None    # de-dupe play_count increments

        # crossfade (seconds) — applied to the backend engine
        self._crossfade = int(self._settings.value("crossfade", 0))
        self.player.backend.set_crossfade(self._crossfade * 1000)

        # equalizer (enable + named preset curve + preamp), restored + applied
        self._eq_enabled = str(self._settings.value("eqEnabled", "false")).lower() == "true"
        self._eq_preset = str(self._settings.value("eqPreset", "Flat"))
        self._eq_preamp = float(self._settings.value("eqPreamp", 0.0))
        self._apply_eq()

        # replaygain mode is instance-level in libVLC → read in __main__ and
        # applied at backend construction; here we only persist the chosen value.
        self._replaygain = str(self._settings.value("replaygainMode", "none"))

        # lyrics for the now-playing track (synced .lrc / embedded / .txt)
        self._lyrics = {"synced": False, "lines": [], "source": ""}

        self._bump.connect(self._refresh_now_playing)
        for ev in ("play_start", "track_change", "stop"):
            self.player.backend.on(ev, self._bump.emit)
        self._notice = ""
        self._backendEvent.connect(self._on_backend_event)
        self.externalCommand.connect(self._on_external_command)
        for ev in ("queue_change", "track_error", "stopped_after", "paused", "resumed"):
            self.player.backend.on(ev, lambda ev=ev: self._backendEvent.emit(ev))
        self.libraryChanged.connect(self.artists.reload)

        # music library folder + background scanning
        self.db_path = None                  # set by run()
        self._music_folder = ""
        self._scanning = False
        self._scan_status = ""
        self._scan_pending = None
        self._fill_while_scanning = False
        self._scanProgress.connect(self._on_scan_progress)
        self._scanDone.connect(self._on_scan_done)

        # tick the queue footer (remaining time) once a second while playing
        self._ticker = QTimer(self)
        self._ticker.setInterval(1000)
        self._ticker.timeout.connect(self.progressChanged)
        self._ticker.start()

    # --- music library folder ---

    def use_music_folder(self, path):
        """The folder in effect at startup (from settings or config.yml)."""
        self._music_folder = path or ""
        self.libraryFolderChanged.emit()

    @Property(str, notify=libraryFolderChanged)
    def musicFolder(self):
        return self._music_folder

    @Property(bool, notify=scanChanged)
    def scanning(self):
        return self._scanning

    @Property(str, notify=scanChanged)
    def scanStatus(self):
        return self._scan_status

    @Slot("QVariant")
    def setMusicFolder(self, folder):
        """Switch the library to `folder` (a QUrl from the folder dialog, or a
        path): remember it, scan it, and drop albums from the old folder."""
        if isinstance(folder, QUrl):
            path = folder.toLocalFile()
        else:
            folder = str(folder or "")
            path = QUrl(folder).toLocalFile() if folder.startswith("file:") else folder
        if not path or not os.path.isdir(path):
            self._scan_status = f"Folder not found: {path}"
            self.scanChanged.emit()
            return
        path = os.path.normpath(path)
        self._settings.setValue("musicFolder", path)
        self._music_folder = path
        self.libraryFolderChanged.emit()
        self.start_index(path, prune=True)

    @Slot()
    def rescanLibrary(self):
        if self._music_folder:
            self.start_index(self._music_folder)

    def start_index(self, path, prune=False):
        """Scan `path` into the library on a background thread (its own sqlite
        connection). A request made while a scan runs is kept and run next."""
        if self._scanning:
            self._scan_pending = (path, prune or bool(self._scan_pending and self._scan_pending[1]))
            return
        self._scanning = True
        self._scan_status = "Scanning…"
        # a first scan fills the empty artist list as it goes; otherwise the
        # list is left alone until the end, so browsing isn't reset under you
        self._fill_while_scanning = self.artists.rowCount() == 0
        self.scanChanged.emit()
        db_path = self.db_path

        def work():
            status = ""
            try:
                c = db.connect(db_path)
                last = [0.0]

                def progress(n_art, n_alb, n_trk):
                    now = time.monotonic()
                    if now - last[0] >= 1.0:
                        last[0] = now
                        self._scanProgress.emit(n_art, n_alb, n_trk)
                try:
                    n_art, n_alb, n_trk = indexer.index_library(c, path, progress)
                    if prune:
                        indexer.prune_outside(c, path)
                finally:
                    c.close()
                status = f"{n_art} artists, {n_alb} albums, {n_trk} tracks"
            except Exception as e:           # an unreadable folder must not kill the app
                status = f"Scan failed: {e}"
            self._scanDone.emit(status)

        threading.Thread(target=work, daemon=True).start()

    def _on_scan_progress(self, n_art, n_alb, n_trk):
        self._scan_status = f"Scanning… {n_art} artists, {n_alb} albums"
        self.scanChanged.emit()
        if self._fill_while_scanning:
            self.artists.reload()

    def _on_scan_done(self, status):
        self._scanning = False
        self._scan_status = status
        self.scanChanged.emit()
        self.libraryChanged.emit()
        if self._scan_pending:
            path, prune = self._scan_pending
            self._scan_pending = None
            self.start_index(path, prune)

    # --- search ---

    @Slot(str)
    def setFilter(self, text):
        self.artists.set_filter(text)

    # --- drill-down: artist → albums grid → song table ---

    @Slot(int, result="QVariantList")
    def artistAlbums(self, artist_id):
        """Album cards for one artist (no track payload — the grid is light)."""
        order = self.ALBUM_ORDERS.get(self._album_sort, self.ALBUM_ORDERS["year"])
        return [{"id": al["id"], "name": al["name"], "year": al["year"],
                 "trackCount": al["n"], "path": al["path"],
                 "coverUrl": f"image://tiles/album/{al['id']}"}
                for al in self.con.execute(
                    "SELECT al.id, al.name, al.year, al.path, COUNT(t.id) n "
                    "FROM albums al LEFT JOIN tracks t ON t.album_id=al.id "
                    f"WHERE al.artist_id=? GROUP BY al.id ORDER BY {order}",
                    (artist_id,))]

    @Slot(int, result="QVariantList")
    def albumSongs(self, album_id):
        """The song-table rows for one album, with metadata columns."""
        return [{"index": i, "trackNo": t["track_no"], "title": t["title"],
                 "duration": t["duration"], "artist": t["artist"],
                 "path": t["path"]}
                for i, t in enumerate(self.con.execute(
                    "SELECT t.track_no, t.title, t.duration, t.path, "
                    "ar.name AS artist FROM tracks t "
                    "JOIN artists ar ON ar.id=t.artist_id "
                    "WHERE t.album_id=? ORDER BY t.disc_no, t.track_no, t.title",
                    (album_id,)))]

    # --- search across artists / albums / songs (req #4) ---

    @Slot(str, result="QVariantMap")
    def search(self, q):
        q = (q or "").strip()
        if not q:
            return {"artists": [], "albums": [], "songs": []}
        like = f"%{q}%"
        artists = [{"id": r["id"], "name": r["name"]} for r in self.con.execute(
            "SELECT id, name FROM artists WHERE name LIKE ? "
            "ORDER BY sort_name LIMIT 24", (like,))]
        albums = [{"id": r["id"], "name": r["name"], "year": r["year"],
                   "artist": r["artist"],
                   "coverUrl": f"image://tiles/album/{r['id']}"}
                  for r in self.con.execute(
                      "SELECT al.id, al.name, al.year, ar.name AS artist "
                      "FROM albums al JOIN artists ar ON ar.id=al.artist_id "
                      "WHERE al.name LIKE ? ORDER BY al.name LIMIT 24", (like,))]
        # a song's index within its album (matches the album's track ordering)
        songs = [{"albumId": r["album_id"], "index": r["idx"], "title": r["title"],
                  "artist": r["artist"], "album": r["album"],
                  "duration": r["duration"], "path": r["path"]}
                 for r in self.con.execute(
                     "SELECT t.title, t.duration, t.path, t.album_id, "
                     "ar.name AS artist, al.name AS album, "
                     "(SELECT COUNT(*) FROM tracks t2 WHERE t2.album_id=t.album_id "
                     " AND (t2.disc_no, t2.track_no, t2.title) "
                     "   < (t.disc_no, t.track_no, t.title)) AS idx "
                     "FROM tracks t JOIN artists ar ON ar.id=t.artist_id "
                     "JOIN albums al ON al.id=t.album_id "
                     "WHERE t.title LIKE ? ORDER BY t.title LIMIT 60", (like,))]
        return {"artists": artists, "albums": albums, "songs": songs}

    # --- playlists (req #1) ---

    @Slot(result="QVariantList")
    def playlists(self):
        return [{"id": p["id"], "name": p["name"], "count": p["n"]}
                for p in self.con.execute(
                    "SELECT pl.id, pl.name, COUNT(pt.track_id) n FROM playlists pl "
                    "LEFT JOIN playlist_tracks pt ON pt.playlist_id=pl.id "
                    "GROUP BY pl.id ORDER BY pl.name")]

    @Slot(int, result="QVariantList")
    def playlistSongs(self, playlist_id):
        return [{"index": i, "trackNo": 0, "title": t["title"],
                 "duration": t["duration"], "artist": t["artist"],
                 "path": t["path"]}
                for i, t in enumerate(self.con.execute(
                    "SELECT t.title, t.duration, t.path, ar.name AS artist "
                    "FROM playlist_tracks pt JOIN tracks t ON t.id=pt.track_id "
                    "JOIN artists ar ON ar.id=t.artist_id "
                    "WHERE pt.playlist_id=? ORDER BY pt.position", (playlist_id,)))]

    @Slot(str, result=int)
    def createPlaylist(self, name):
        pid = db.create_playlist(self.con, name or "New Playlist")
        self.playlistsChanged.emit()
        return pid

    @Slot(int, str)
    def addToPlaylist(self, playlist_id, path):
        row = self.con.execute("SELECT id FROM tracks WHERE path=?",
                               (path,)).fetchone()
        if row:
            db.append_to_playlist(self.con, playlist_id, row["id"])
            self.playlistsChanged.emit()

    @Slot(int, str)
    def addAlbumToPlaylist(self, playlist_id, album_path):
        ids = [r["id"] for r in self.con.execute(
            "SELECT t.id FROM tracks t JOIN albums al ON al.id=t.album_id "
            "WHERE al.path=? ORDER BY t.disc_no, t.track_no, t.title", (album_path,))]
        db.append_many_to_playlist(self.con, playlist_id, ids)
        self.playlistsChanged.emit()

    @Slot(int, int)
    def addArtistToPlaylist(self, playlist_id, artist_id):
        for r in self.con.execute(
                "SELECT t.id FROM tracks t JOIN albums al ON al.id=t.album_id "
                "WHERE t.artist_id=? ORDER BY al.year, al.name, t.disc_no, "
                "t.track_no, t.title", (artist_id,)):
            db.append_to_playlist(self.con, playlist_id, r["id"])
        self.playlistsChanged.emit()

    @Slot(int, "QVariantList")
    def addTracksToPlaylist(self, playlist_id, paths):
        for p in paths:
            row = self.con.execute("SELECT id FROM tracks WHERE path=?",
                                   (p,)).fetchone()
            if row:
                db.append_to_playlist(self.con, playlist_id, row["id"])
        self.playlistsChanged.emit()

    @Slot(int, int, int)
    def movePlaylistTrack(self, playlist_id, frm, to):
        """Reorder a playlist by moving the track at `frm` to `to` (drag-drop)."""
        ids = db.playlist_track_ids(self.con, playlist_id)
        if not (0 <= frm < len(ids)) or not (0 <= to < len(ids)) or frm == to:
            return
        ids.insert(to, ids.pop(frm))
        self.con.execute("DELETE FROM playlist_tracks WHERE playlist_id=?",
                         (playlist_id,))
        for pos, tid in enumerate(ids):
            self.con.execute(
                "INSERT INTO playlist_tracks(playlist_id, track_id, position) "
                "VALUES (?,?,?)", (playlist_id, tid, pos))
        self.con.commit()
        self.playlistsChanged.emit()
        self.songsChanged.emit()

    # --- metadata / Picard (req #2) ---

    @Slot(str)
    def openInPicard(self, path):
        """Launch MusicBrainz Picard on a file (or album folder), if installed."""
        if shutil.which("picard"):
            subprocess.Popen(["picard", path])

    @Slot(str, result="QVariantMap")
    def trackMetadata(self, path):
        return meta.read(path)

    @Slot(str, str, str, str, str)
    def saveMetadata(self, path, title, artist, album, track):
        if meta.write(path, title=title, artist=artist, album=album, track=track):
            # Keep the index in step with the edited tags. Artist and album come
            # from the folders in this library, so only title and track number
            # live in the database; recording the new modified time stops the
            # next scan re-reading a file that's already up to date.
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0
            self.con.execute("UPDATE tracks SET title=?, track_no=?, mtime=? WHERE path=?",
                             (title, int(track) if track.isdigit() else 0, mtime, path))
            self.con.commit()
            backend = self.player.backend
            if hasattr(backend, "invalidate_metadata"):
                backend.invalidate_metadata(path)
            for t in self.player.queue:
                if t.get("path") == path:
                    t["title"] = title
            cur = self._current_track()
            if cur and cur.get("path") == path:
                self._np_title = title
                self.nowPlayingChanged.emit()
            self.queue.reload()
            self.songsChanged.emit()

    # --- playback ---

    @Slot(int, int)
    def playAlbum(self, album_id, start):
        row = self.con.execute("SELECT path, name, artist_id FROM albums WHERE id=?",
                               (album_id,)).fetchone()
        if not row:
            return
        album_path = row["path"]
        tracks = [{"title": t["title"], "track_no": t["track_no"],
                   "path": t["path"], "duration": t["duration"],
                   "artist": t["artist"], "album_path": album_path,
                   "album_id": album_id, "artist_id": row["artist_id"],
                   "album_name": row["name"]}
                  for t in self.con.execute(
                      "SELECT t.title, t.track_no, t.path, t.duration, "
                      "ar.name AS artist FROM tracks t "
                      "JOIN artists ar ON ar.id=t.artist_id "
                      "WHERE t.album_id=? ORDER BY t.disc_no, t.track_no, t.title",
                      (album_id,))]
        if not tracks:
            return
        self._np_playlist_id = -1
        self.player.set_queue(tracks, start=start, album_path=album_path)
        self.queue.reload()
        self.queueChanged.emit()

    @Slot(int, int)
    def playPlaylist(self, playlist_id, start):
        """Play a playlist as a mixed-album queue. Each track keeps its own album
        context so the now-playing art + vinyl follow the current track."""
        tracks = [{"title": t["title"], "track_no": 0, "path": t["path"],
                   "duration": t["duration"], "artist": t["artist"],
                   "album_path": t["album_path"], "album_id": t["album_id"],
                   "artist_id": t["artist_id"], "album_name": t["album_name"]}
                  for t in self.con.execute(
                      "SELECT t.title, t.path, t.duration, ar.name AS artist, "
                      "al.id AS album_id, al.path AS album_path, "
                      "al.name AS album_name, t.artist_id "
                      "FROM playlist_tracks pt JOIN tracks t ON t.id=pt.track_id "
                      "JOIN artists ar ON ar.id=t.artist_id "
                      "JOIN albums al ON al.id=t.album_id "
                      "WHERE pt.playlist_id=? ORDER BY pt.position", (playlist_id,))]
        if not tracks:
            return
        self._np_playlist_id = playlist_id
        # album_path stays None (mixed albums); per-track album context drives
        # the now-playing art/vinyl via _refresh_now_playing.
        self.player.set_queue(tracks, start=start, album_path=None)
        self.queue.reload()
        self.queueChanged.emit()

    @Slot(int)
    def jumpTo(self, index):
        self.player.jump_to(index)
        self.queue.reload()
        self.queueChanged.emit()

    # --- editing the queue ---

    @Slot(int)
    def removeFromQueue(self, index):
        self.player.remove(index)
        self.queue.reload()
        self.queueChanged.emit()
        if not self.player.queue:
            self._refresh_now_playing()

    @Slot(int, int)
    def moveInQueue(self, src, dst):
        self.player.move(src, dst)
        self.queue.reload()
        self.queueChanged.emit()

    @Slot()
    def clearQueue(self):
        self.player.clear()
        self._np_playlist_id = -1
        self.transportChanged.emit()
        self._refresh_now_playing()

    @Property(bool, notify=transportChanged)
    def stopAfterCurrent(self):
        return bool(getattr(self.player, "stop_after_current", False))

    @Slot()
    def toggleStopAfterCurrent(self):
        self.player.set_stop_after_current(not self.stopAfterCurrent)
        self.transportChanged.emit()

    # --- notices ---

    @Property(str, notify=noticeChanged)
    def notice(self):
        return self._notice

    def _set_notice(self, text):
        self._notice = text
        self.noticeChanged.emit()

    @Slot()
    def clearNotice(self):
        if self._notice:
            self._set_notice("")

    def _on_backend_event(self, event):
        """Backend events that aren't a track change, on the GUI thread."""
        if event == "track_error":
            idx, path = getattr(self.player.backend, "last_error", None) or (-1, None)
            q = self.player.queue
            title = q[idx].get("title") if 0 <= idx < len(q) else None
            name = title or (os.path.basename(path) if path else "a track")
            self._set_notice(f"Skipped \u201c{name}\u201d: the file couldn't be played.")
        elif event == "stopped_after":
            self.transportChanged.emit()
        if event in ("paused", "resumed", "stopped_after"):
            self.progressChanged.emit()
        self.queue.reload()
        self.queueChanged.emit()

    def _on_external_command(self, name, value):
        """Requests from outside the window, such as desktop media controls."""
        if name == "repeat":
            self.player.set_repeat(value)
            self._settings.setValue("repeat", self.player.repeat)
            self.transportChanged.emit()
        elif name == "shuffle":
            self.setShuffle(value == "true")
        elif name == "raise":
            self.raiseRequested.emit()

    def _current_track(self):
        i = self.player.index
        q = self.player.queue
        return q[i] if 0 <= i < len(q) else None

    def vinyl_now(self):
        """Everything the VinylItem needs for the *current track's* album: art,
        album path/name, artist, and the resolved settings. Works for playlists
        (mixed albums) because each queued track carries its own album context."""
        cur = self._current_track()
        if not cur or not cur.get("album_path"):
            return None
        ap = cur["album_path"]
        d = db.resolve_vinyl_settings(
            self.con, album_id=cur.get("album_id"), artist_id=cur.get("artist_id"),
            playlist_id=self._np_playlist_id if self._np_playlist_id >= 0 else None)
        return {
            "album_path": ap,
            "art_path": self.player.backend.find_album_art(ap),
            "artist": cur.get("artist"), "album": cur.get("album_name"),
            "settings": VinylSettings.from_dict(d),
        }

    # --- vinyl override UI (req #7) ---

    @Property("QVariantList", constant=True)
    def vinylCatalog(self):
        """The full vinyl style catalog, grouped into sections — mirrors lp's web
        picker. Values are real `_pick_vinyl_style` overrides."""
        def _items(pairs):
            return [{"value": v, "label": lbl} for v, lbl in pairs]

        basic = [("random", "Random"), ("black", "Black"), ("clear", "Clear"),
                 ("picture", "Album Art"), ("color", "Random Colour"),
                 ("mandelbrot", "Random Mandelbrot"), ("nebula", "Random Nebula"),
                 ("munafo", "Random Munafo")]
        colours = [(f"color-{n}", n.replace("-", " ").title()) for n in VINYL_COLORS]
        mandelbrot = [(f"mandelbrot-{v[4]}-{v[5]}",
                       v[4].replace("-", " ").title() + " " + v[5].title())
                      for v in MANDELBROT_VARIANTS]
        nebula = [(f"nebula-{v[2]}", v[2].replace("-", " ").title())
                  for v in NEBULA_VARIANTS]
        munafo = [(f"munafo-{v[0]}", v[2] if len(v) > 2 else v[0])
                  for v in MUNAFO_VARIANTS]
        return [
            {"title": "Basic", "items": _items(basic)},
            {"title": "Coloured", "items": _items(colours)},
            {"title": "Mandelbrot", "items": _items(mandelbrot)},
            {"title": "Nebula", "items": _items(nebula)},
            {"title": "Munafo Deep-Zoom", "items": _items(munafo)},
        ]

    @Property("QVariantList", constant=True)
    def vinylLabels(self):
        return [{"value": "art", "label": "Album art"}] + [
            {"value": f"label-{c}", "label": c.title()} for c in LABEL_COLORS.keys()]

    @Property(int, notify=nowPlayingChanged)
    def npAlbumId(self):
        return self._np_album_id

    @Property(int, notify=nowPlayingChanged)
    def npPlaylistId(self):
        return self._np_playlist_id

    @Slot(result="QVariantMap")
    def currentVinyl(self):
        """The vinyl settings in effect for the now-playing track (for the UI)."""
        spec = self.vinyl_now()
        s = spec["settings"] if spec else VinylSettings()
        return {"style": s.style, "label": s.label, "brightness": s.brightness,
                "effects": list(s.effects), "grooves": s.grooves}

    @Slot(str, str, str, int)
    def setVinyl(self, scope, style, label, brightness):
        """Write a vinyl override at scope ∈ {global, artist, album, playlist} and
        re-render. Merges onto the current settings so unset fields persist."""
        spec = self.vinyl_now()
        base = (spec["settings"] if spec else VinylSettings()).to_dict()
        base["style"] = style
        base["label"] = label
        base["brightness"] = brightness
        scope_id = {"global": None, "artist": self._np_artist_id,
                    "album": self._np_album_id,
                    "playlist": self._np_playlist_id}.get(scope)
        if scope != "global" and (scope_id is None or scope_id < 0):
            return
        db.set_vinyl_override(self.con, scope, scope_id, base)
        self.vinylChanged.emit()

    @Property("QVariantList", constant=True)
    def vinylEffects(self):
        """Vinyl Effects, finishes the chooser offers on top of any style."""
        from lpcore.vinyl.catalog import VINYL_EFFECTS
        return [{"value": k, "label": v} for k, v in VINYL_EFFECTS.items()]

    @Property("QVariantList", constant=True)
    def vinylGrooves(self):
        """Groove treatments: how the grooves catch the light, one per record."""
        from lpcore.vinyl.catalog import GROOVE_TREATMENTS
        return [{"value": k, "label": v} for k, v in GROOVE_TREATMENTS.items()]

    @Slot(str, "QVariantList")
    def setVinylEffects(self, scope, effects):
        """Write the Vinyl Effects at scope, keeping every other setting there."""
        self._save_vinyl_change(scope, effects=list(effects))

    @Slot(str, str)
    def setVinylGrooves(self, scope, grooves):
        """Write the groove treatment at scope, keeping every other setting there."""
        self._save_vinyl_change(scope, grooves=grooves)

    def _save_vinyl_change(self, scope, **changes):
        spec = self.vinyl_now()
        current = VinylSettings.from_dict((spec["settings"] if spec else VinylSettings()).to_dict())
        try:
            current.update(**changes)
        except ValueError:
            return
        scope_id = {"global": None, "artist": self._np_artist_id,
                    "album": self._np_album_id,
                    "playlist": self._np_playlist_id}.get(scope)
        if scope != "global" and (scope_id is None or scope_id < 0):
            return
        db.set_vinyl_override(self.con, scope, scope_id, current.to_dict())
        self.vinylChanged.emit()

    # --- add to queue / play next (req: queue ops) ---

    def _album_track_dicts(self, album_id):
        row = self.con.execute(
            "SELECT path, name, artist_id FROM albums WHERE id=?",
            (album_id,)).fetchone()
        if not row:
            return []
        return [{"title": t["title"], "track_no": t["track_no"], "path": t["path"],
                 "duration": t["duration"], "artist": t["artist"],
                 "album_path": row["path"], "album_id": album_id,
                 "artist_id": row["artist_id"], "album_name": row["name"]}
                for t in self.con.execute(
                    "SELECT t.track_no, t.title, t.duration, t.path, ar.name AS artist "
                    "FROM tracks t JOIN artists ar ON ar.id=t.artist_id "
                    "WHERE t.album_id=? ORDER BY t.disc_no, t.track_no, t.title",
                    (album_id,))]

    def _track_dicts_for_paths(self, paths):
        """Track dicts for `paths`, in the given order (unknown paths dropped):
        one query per chunk of paths rather than one per path."""
        found = {}
        for i in range(0, len(paths), 500):
            chunk = paths[i:i + 500]
            marks = ",".join("?" * len(chunk))
            for r in self.con.execute(
                    "SELECT t.title, t.track_no, t.duration, t.path, t.album_id, "
                    "t.artist_id, al.path AS album_path, al.name AS album_name, "
                    "ar.name AS artist FROM tracks t "
                    "JOIN albums al ON al.id=t.album_id "
                    f"JOIN artists ar ON ar.id=t.artist_id WHERE t.path IN ({marks})", chunk):
                found[r["path"]] = {"title": r["title"], "track_no": r["track_no"],
                                    "path": r["path"], "duration": r["duration"],
                                    "artist": r["artist"], "album_path": r["album_path"],
                                    "album_id": r["album_id"], "artist_id": r["artist_id"],
                                    "album_name": r["album_name"]}
        return [dict(found[p]) for p in paths if p in found]

    @Slot(int, bool)
    def queueAlbum(self, album_id, play_next):
        self.player.add_tracks(self._album_track_dicts(album_id), play_next=play_next)
        self.queue.reload()
        self.queueChanged.emit()

    @Slot("QVariantList", bool)
    def queueTracks(self, paths, play_next):
        self.player.add_tracks(self._track_dicts_for_paths(list(paths)),
                               play_next=play_next)
        self.queue.reload()
        self.queueChanged.emit()

    @Slot(result="QVariantList")
    def playTrackList(self, *_):           # placeholder kept for symmetry
        return []

    @Slot("QVariantList", int)
    def playPaths(self, paths, start):
        """Play an arbitrary list of track paths (smart lists: favourites,
        recently played, a genre) as a mixed-album queue."""
        tracks = self._track_dicts_for_paths(list(paths))
        if not tracks:
            return
        self._np_playlist_id = -1
        self.player.set_queue(tracks, start=start, album_path=None)
        self.queue.reload()
        self.queueChanged.emit()

    # --- shuffle / repeat / volume / mute (transport) ---

    @Property(bool, notify=transportChanged)
    def shuffle(self):
        return self.player.shuffle

    @Slot(bool)
    def setShuffle(self, on):
        self.player.set_shuffle(on)
        self.queue.reload()
        self.queueChanged.emit()
        self.transportChanged.emit()

    @Property(str, notify=transportChanged)
    def repeatMode(self):
        return self.player.repeat

    @Slot()
    def cycleRepeat(self):
        mode = self.player.cycle_repeat()
        self._settings.setValue("repeat", mode)
        self.transportChanged.emit()

    @Property(int, notify=transportChanged)
    def volume(self):
        return self._volume

    @Slot(int)
    def setVolume(self, vol):
        self._volume = max(0, min(100, int(vol)))
        self.player.set_volume(self._volume)
        self._settings.setValue("volume", self._volume)
        self.transportChanged.emit()

    @Slot()
    def toggleMute(self):
        self.player.toggle_mute()
        self.transportChanged.emit()

    @Property(bool, notify=transportChanged)
    def muted(self):
        return self.player.backend.is_muted()

    @Slot(float)
    def seek(self, frac):
        self.player.seek(frac)
        self.progressChanged.emit()

    @Slot(float)
    def seekBy(self, seconds):
        """Forward or back within the playing track (keyboard shortcuts)."""
        self.player.seek_by(seconds)
        self.progressChanged.emit()

    # --- favorites / ratings / play stats ---

    def _record_play(self, path):
        if not path or path == self._last_played_path:
            return
        self._last_played_path = path
        tid = db.track_id_for_path(self.con, path)
        if tid is not None:
            db.record_play(self.con, tid, time.time())

    @Slot(str, result=bool)
    def isFavorite(self, path):
        r = self.con.execute("SELECT favorite FROM tracks WHERE path=?",
                             (path,)).fetchone()
        return bool(r and r["favorite"])

    @Slot(str)
    def toggleFavorite(self, path):
        tid = db.track_id_for_path(self.con, path)
        if tid is None:
            return
        cur = self.con.execute("SELECT favorite FROM tracks WHERE id=?",
                              (tid,)).fetchone()["favorite"]
        db.set_favorite(self.con, tid, not cur)
        self.songsChanged.emit()
        self.nowPlayingChanged.emit()

    @Slot(str, int)
    def rateTrack(self, path, rating):
        tid = db.track_id_for_path(self.con, path)
        if tid is not None:
            db.set_rating(self.con, tid, rating)
            self.songsChanged.emit()

    @Property(bool, notify=nowPlayingChanged)
    def npIsFavorite(self):
        cur = self._current_track()
        return self.isFavorite(cur["path"]) if cur and cur.get("path") else False

    @Slot()
    def toggleFavoriteCurrent(self):
        cur = self._current_track()
        if cur and cur.get("path"):
            self.toggleFavorite(cur["path"])

    # --- smart lists (favourites / recently played / most played / added) ---

    @staticmethod
    def _rows_to_songtable(rows):
        return [{"index": i, "trackNo": 0, "title": r["title"],
                 "duration": r["duration"], "artist": r["artist"],
                 "path": r["path"]} for i, r in enumerate(rows)]

    @Slot(str, result="QVariantList")
    def smartList(self, kind):
        fn = {"favorites": db.favorites, "recent": db.recently_played,
              "most": db.most_played, "added": db.recently_added}.get(kind)
        return self._rows_to_songtable(fn(self.con)) if fn else []

    @Slot(result="QVariantList")
    def genreList(self):
        return [{"name": g} for g in db.genres(self.con)]

    @Slot(str, result="QVariantList")
    def genreSongs(self, genre):
        return self._rows_to_songtable(db.genre_tracks(self.con, genre))

    # --- playlist management ---

    @Slot(int, str)
    def renamePlaylist(self, playlist_id, name):
        db.rename_playlist(self.con, playlist_id, name or "Playlist")
        self.playlistsChanged.emit()

    @Slot(int)
    def deletePlaylist(self, playlist_id):
        db.delete_playlist(self.con, playlist_id)
        self.playlistsChanged.emit()

    @Slot(int, int)
    def removeFromPlaylist(self, playlist_id, position):
        db.remove_playlist_position(self.con, playlist_id, position)
        self.playlistsChanged.emit()
        self.songsChanged.emit()

    # --- equalizer ---

    def _apply_eq(self):
        bands = EQ_PRESETS.get(self._eq_preset, EQ_PRESETS["Flat"])
        self.player.backend.set_equalizer(self._eq_enabled, preamp=self._eq_preamp,
                                          bands=bands)

    @Property("QVariantList", constant=True)
    def eqPresets(self):
        return list(EQ_PRESETS.keys())

    @Property("QVariantList", constant=True)
    def eqFrequencies(self):
        return self.player.backend.eq_bands()

    @Property(bool, notify=transportChanged)
    def eqEnabled(self):
        return self._eq_enabled

    @Slot(bool)
    def setEqEnabled(self, on):
        self._eq_enabled = bool(on)
        self._settings.setValue("eqEnabled", "true" if on else "false")
        self._apply_eq()
        self.transportChanged.emit()

    @Property(str, notify=transportChanged)
    def eqPreset(self):
        return self._eq_preset

    @Slot(str)
    def setEqPreset(self, name):
        if name in EQ_PRESETS:
            self._eq_preset = name
            self._settings.setValue("eqPreset", name)
            self._apply_eq()
            self.transportChanged.emit()

    @Property("QVariantList", notify=transportChanged)
    def eqCurrentBands(self):
        return EQ_PRESETS.get(self._eq_preset, EQ_PRESETS["Flat"])

    @Property(float, notify=transportChanged)
    def eqPreamp(self):
        return self._eq_preamp

    @Slot(float)
    def setEqPreamp(self, db_val):
        self._eq_preamp = float(db_val)
        self._settings.setValue("eqPreamp", self._eq_preamp)
        self._apply_eq()
        self.transportChanged.emit()

    # --- crossfade ---

    @Property(int, notify=transportChanged)
    def crossfade(self):
        return self._crossfade

    @Slot(int)
    def setCrossfade(self, seconds):
        self._crossfade = max(0, min(12, int(seconds)))
        self._settings.setValue("crossfade", self._crossfade)
        self.player.backend.set_crossfade(self._crossfade * 1000)
        self.queue.reload()
        self.queueChanged.emit()
        self.transportChanged.emit()

    # --- replaygain (instance-level: applies on next launch) ---

    @Property(str, notify=transportChanged)
    def replayGainMode(self):
        return self._replaygain

    @Slot(str)
    def setReplayGainMode(self, mode):
        if mode in ("none", "track", "album"):
            self._replaygain = mode
            self._settings.setValue("replaygainMode", mode)
            self.transportChanged.emit()

    # --- lyrics (synced .lrc / embedded / .txt) ---

    def _load_lyrics(self, path):
        if not path:
            self._lyrics = {"synced": False, "lines": [], "source": ""}
            return
        try:
            self._lyrics = lyrics_mod.load_lyrics(path)
        except Exception:
            self._lyrics = {"synced": False, "lines": [], "source": ""}

    @Property("QVariantList", notify=nowPlayingChanged)
    def lyricsLines(self):
        return [{"time": (-1.0 if t is None else float(t)), "text": text}
                for t, text in self._lyrics.get("lines", [])]

    @Property(bool, notify=nowPlayingChanged)
    def lyricsSynced(self):
        return bool(self._lyrics.get("synced"))

    @Property(bool, notify=nowPlayingChanged)
    def hasLyrics(self):
        return len(self._lyrics.get("lines", [])) > 0

    @Property(int, notify=progressChanged)
    def lyricIndex(self):
        if not self._lyrics.get("synced"):
            return -1
        t = self.player.backend.get_current_time()
        return lyrics_mod.active_index(self._lyrics.get("lines", []), t)

    @Slot()
    def playPause(self):
        self.player.toggle()
        self.progressChanged.emit()

    @Property(bool, notify=progressChanged)
    def npIsPlaying(self):
        return self.player.backend.is_actively_playing()

    @Slot()
    def next(self):
        self.player.next()

    @Slot()
    def previous(self):
        self.player.previous()

    # --- now-playing (properties read by QML) ---

    def _refresh_now_playing(self):
        backend = self.player.backend
        cur = self._current_track()
        loaded = (backend.is_loaded() if hasattr(backend, "is_loaded")
                  else bool(backend.get_status().get("playing")))
        if loaded:
            if cur:
                # the library already has these, so the file's tags aren't re-read
                self._np_title = cur.get("title") or os.path.splitext(
                    os.path.basename(cur.get("path") or ""))[0]
                self._np_sub = " — ".join(
                    x for x in (cur.get("artist"), cur.get("album_name")) if x)
            else:
                st = backend.get_status()
                self._np_title = st.get("track_title") or ""
                self._np_sub = " — ".join(
                    x for x in (st.get("artist"), st.get("album")) if x)
            # follow the current track's album (so playlists get art + vinyl too)
            if cur:
                self._np_album_id = cur.get("album_id", -1)
                self._np_artist_id = cur.get("artist_id", -1)
                self._np_accent = self._accent_for_album(
                    self._np_album_id, cur.get("album_path"))
                self._record_play(cur.get("path"))
                self._load_lyrics(cur.get("path"))
        else:
            self._np_title = ""
            self._np_sub = ""
            self._lyrics = {"synced": False, "lines": [], "source": ""}
        self.queue.reload()              # move the ▶ marker to the current row
        self.nowPlayingChanged.emit()
        self.queueChanged.emit()
        self.progressChanged.emit()

    def _accent_for_album(self, album_id, album_path):
        """A representative tint colour for gradients — the album art's average
        colour, nudged toward a usable saturation. Cached per album."""
        if album_id in self._accent_cache:
            return self._accent_cache[album_id]
        accent = "#E0A24C"
        art = self.player.backend.find_album_art(album_path) if album_path else None
        if art:
            # decode a thumbnail, not the full-size cover: only its average colour is used
            reader = QImageReader(art)
            reader.setScaledSize(QSize(24, 24))
            img = reader.read()
            if not img.isNull():
                px = img.scaled(1, 1, Qt.IgnoreAspectRatio,
                                Qt.SmoothTransformation).pixelColor(0, 0)
                # lift very dark/desaturated averages so the tint reads
                h, s, v, _ = px.getHsv()
                px = QColor.fromHsv(h, min(255, int(s * 1.3)), max(70, v))
                accent = px.name()
        if album_id >= 0:
            self._accent_cache[album_id] = accent
        return accent

    @Property(str, notify=nowPlayingChanged)
    def npAccent(self):
        return self._np_accent

    @Property("QVariantList", notify=queueChanged)
    def trackMarkers(self):
        """Fractions (0–1) of the track boundaries within the queue, for the
        seek bar's per-track tick marks. Skips the leading 0."""
        b = list(self.player.backend.track_boundaries or [])
        total = self.player.backend.album_duration or 0
        return [x / total for x in b[1:]] if total else []

    # --- queue footer (req #3): N/M remaining, time remaining/total ---

    def _progress(self):
        """Queue progress, without the tag read get_status() would do."""
        backend = self.player.backend
        if hasattr(backend, "get_album_progress"):
            return backend.get_album_progress() or {}
        return (backend.get_status() or {}).get("progress", {})

    @Property(int, notify=queueChanged)
    def queueCount(self):
        return len(self.player.queue)

    @Property(int, notify=progressChanged)
    def tracksRemaining(self):
        n = len(self.player.queue)
        return max(0, n - (self.player.index + 1)) if n else 0

    @Property(str, notify=progressChanged)
    def timeRemaining(self):
        prog = self._progress()
        return _mmss(prog.get("album_duration", 0) - prog.get("elapsed", 0))

    @Property(str, notify=progressChanged)
    def timeTotal(self):
        prog = self._progress()
        total = prog.get("album_duration") or sum(
            t.get("duration") or 0 for t in self.player.queue)
        return _mmss(total)

    @Property(float, notify=progressChanged)
    def npPosition(self):
        """0–1 progress through the current queue (for the seek/progress bar)."""
        prog = self._progress()
        total = prog.get("album_duration", 0)
        return (prog.get("elapsed", 0) / total) if total else 0.0

    @Property(str, notify=progressChanged)
    def timeElapsed(self):
        prog = self._progress()
        return _mmss(prog.get("elapsed", 0))

    # --- view settings (sort + grid size + theme; persisted) ---

    @Property(bool, notify=settingsChanged)
    def darkMode(self):
        return self._dark

    @Slot(bool)
    def setDarkMode(self, on):
        if on != self._dark:
            self._dark = on
            self._settings.setValue("darkMode", "true" if on else "false")
            self.settingsChanged.emit()

    @Property(int, notify=settingsChanged)
    def gridTile(self):
        return self._grid_tile

    @Slot(int)
    def setGridTile(self, px):
        if px != self._grid_tile:
            self._grid_tile = px
            self._settings.setValue("gridTile", px)
            self.settingsChanged.emit()

    @Property(str, notify=settingsChanged)
    def artistSort(self):
        return self._artist_sort

    @Slot(str)
    def setArtistSort(self, key):
        if key != self._artist_sort:
            self._artist_sort = key
            self._settings.setValue("artistSort", key)
            self.artists.set_sort(key)
            self.artists.reload()
            self.settingsChanged.emit()

    @Property(str, notify=settingsChanged)
    def albumSort(self):
        return self._album_sort

    @Slot(str)
    def setAlbumSort(self, key):
        if key != self._album_sort:
            self._album_sort = key
            self._settings.setValue("albumSort", key)
            self.settingsChanged.emit()

    @Property(str, notify=nowPlayingChanged)
    def npTitle(self):
        return self._np_title

    @Property(str, notify=nowPlayingChanged)
    def npSub(self):
        return self._np_sub

    @Property(str, notify=nowPlayingChanged)
    def npCoverUrl(self):
        return (f"image://tiles/album/{self._np_album_id}"
                if self._np_album_id >= 0 else "")


def run(con, player, db_path, on_ready=None):
    """Build the QML app and run its event loop. `on_ready(controller)` is
    called once the window exists (used to kick off background indexing)."""
    QQuickStyle.setStyle("Basic")        # neutral base; lp-deck styles its own dark theme
    app = QGuiApplication.instance() or QGuiApplication([])
    app.setOrganizationName("lp-deck")   # QSettings path
    app.setApplicationName("lp-deck")
    qmlRegisterType(VinylItem, "Lpdeck", 1, 0, "VinylItem")

    artists = ArtistsModel(con)
    queue = QueueModel(player)
    controller = Controller(con, player, artists, queue)
    controller.db_path = db_path

    engine = QQmlApplicationEngine()
    engine.addImageProvider("tiles", TileProvider(db_path))
    engine.addImageProvider("vinyl", VinylPreviewProvider(db_path))
    ctx = engine.rootContext()
    ctx.setContextProperty("artistsModel", artists)
    ctx.setContextProperty("queueModel", queue)
    ctx.setContextProperty("controller", controller)
    engine.load(os.path.join(QML_DIR, "Main.qml"))
    if not engine.rootObjects():
        raise RuntimeError("failed to load Main.qml")

    if on_ready:
        on_ready(controller)
    return app.exec()
