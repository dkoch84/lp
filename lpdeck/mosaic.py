"""Artist/album tile rendering.

Each artist is shown as a square tile built from its album covers: a single
cover fills the tile, otherwise a 2×2 montage (covers are cycled to fill all
four cells, so there are never blank quadrants). Albums show their cover, or a
vinyl-disc glyph. Artists with no art get a palette-tinted person silhouette.

Everything renders onto QImage (not QPixmap) so it is safe to call from a
QQuickImageProvider worker thread; QPixmap convenience wrappers are provided for
the legacy QWidgets path, which must run on the GUI thread.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPainterPath


def _square(path, size):
    """Load `path`, scale-to-cover and centre-crop to a `size`×`size` QImage."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        return None
    img = img.scaled(size, size, Qt.KeepAspectRatioByExpanding,
                     Qt.SmoothTransformation)
    x = (img.width() - size) // 2
    y = (img.height() - size) // 2
    return img.copy(x, y, size, size)


def _canvas(size):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    return img


def _tint():
    """(bg, accent) colours for art-less tiles — fixed to lp-deck's dark theme
    (see qml/Theme.qml: surface + vinyl-amber accent)."""
    accent = QColor("#E0A24C")
    accent.setAlpha(130)
    return QColor("#242730"), accent


def _placeholder(p, size):
    """A muted person silhouette over alternate-base (artist, no art)."""
    bg, accent = _tint()
    p.fillRect(0, 0, size, size, bg)
    p.setBrush(accent)
    p.setPen(Qt.NoPen)
    cx, head_r = size / 2, size * 0.15
    head_cy = size * 0.40
    p.drawEllipse(QPointF(cx, head_cy), head_r, head_r)
    body = QPainterPath()
    bw, bh = size * 0.54, size * 0.70
    body.addEllipse(QRectF(cx - bw / 2, head_cy + head_r * 0.6, bw, bh))
    p.setClipRect(QRectF(0, 0, size, size * 0.95))
    p.drawPath(body)


def _disc(p, size):
    """A muted vinyl-record glyph over alternate-base (album, no art)."""
    bg, accent = _tint()
    p.fillRect(0, 0, size, size, bg)
    p.setBrush(accent)
    p.setPen(Qt.NoPen)
    cx = cy = size / 2
    p.drawEllipse(QPointF(cx, cy), size * 0.34, size * 0.34)
    p.setBrush(bg)
    p.drawEllipse(QPointF(cx, cy), size * 0.30, size * 0.30)
    p.setBrush(accent)
    p.drawEllipse(QPointF(cx, cy), size * 0.27, size * 0.27)
    p.setBrush(bg)
    p.drawEllipse(QPointF(cx, cy), size * 0.05, size * 0.05)


def artist_image(cover_paths, size):
    """Square QImage for an artist: full cover, 2×2 montage, or silhouette."""
    img = _canvas(size)
    p = QPainter(img)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    squares = [s for c in cover_paths if (s := _square(c, size)) is not None]
    if not squares:
        _placeholder(p, size)
    elif len(squares) == 1:
        p.drawImage(0, 0, squares[0])
    else:
        half = size // 2
        for i, (x, y) in enumerate(((0, 0), (half, 0), (0, half), (half, half))):
            quad = squares[i % len(squares)].scaled(
                half, half, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawImage(x, y, quad)
    p.end()
    return img


def album_image(cover_path, size):
    """Square QImage for an album: its cover, or a vinyl-disc placeholder."""
    img = _canvas(size)
    p = QPainter(img)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    sq = _square(cover_path, size) if cover_path else None
    if sq is not None:
        p.drawImage(0, 0, sq)
    else:
        _disc(p, size)
    p.end()
    return img
