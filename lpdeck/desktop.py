"""The system tray icon and track-change notifications.

The tray menu has the transport, a way back to the window and Quit; clicking the
icon brings the window forward. Notifications go through the tray when it's
showing (the desktop's own notification service behind it), and through
notify-send otherwise.
"""
import shutil
import subprocess

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def app_icon():
    return QIcon.fromTheme("lp-deck", QIcon.fromTheme("audio-x-generic",
                           QIcon.fromTheme("media-playback-start")))


class Tray(QObject):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self._icon = QSystemTrayIcon(app_icon(), self)
        self._icon.setToolTip("lp-deck")
        self._icon.activated.connect(self._on_activated)

        menu = QMenu()
        self._play = QAction("Play or pause", menu)
        self._play.triggered.connect(controller.playPause)
        previous = QAction("Previous", menu)
        previous.triggered.connect(controller.previous)
        nxt = QAction("Next", menu)
        nxt.triggered.connect(controller.next)
        show = QAction("Show lp-deck", menu)
        show.triggered.connect(controller.raiseRequested.emit)
        quit_ = QAction("Quit", menu)
        quit_.triggered.connect(QApplication.quit)
        for action in (self._play, previous, nxt):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(show)
        menu.addAction(quit_)
        self._menu = menu                      # the tray doesn't own its menu
        self._icon.setContextMenu(menu)

    @property
    def visible(self):
        return self.available and self._icon.isVisible()

    def set_visible(self, on):
        if self.available:
            self._icon.setVisible(bool(on))

    def set_tooltip(self, text):
        self._icon.setToolTip(text or "lp-deck")

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._controller.raiseRequested.emit()
        elif reason == QSystemTrayIcon.MiddleClick:
            self._controller.playPause()

    def notify(self, title, body, icon_path=None):
        """Show a short desktop notification."""
        if self.visible and QSystemTrayIcon.supportsMessages():
            icon = QIcon(icon_path) if icon_path else app_icon()
            self._icon.showMessage(title, body, icon, 5000)
            return
        exe = shutil.which("notify-send")
        if exe:
            args = [exe, "--app-name=lp-deck", "--expire-time=5000"]
            if icon_path:
                args.append(f"--icon={icon_path}")
            subprocess.Popen(args + [title, body], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
