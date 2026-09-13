"""One lp-deck at a time.

A second launch (from a file manager's "Open with", or the command line with
files) hands its files to the lp-deck already running and exits, instead of
opening a second window that would fight over the database and media keys.
"""
import json
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name():
    return f"lp-deck-{os.getuid()}"


def send_to_running(paths, name=None, timeout_ms=1000):
    """Hand `paths` to a running lp-deck. True if one was there to take them."""
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(json.dumps({"open": [os.path.abspath(p) for p in paths]}).encode())
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """Listens for later launches; `opened` carries the paths they were given."""
    opened = Signal(list)

    def __init__(self, name=None, parent=None):
        super().__init__(parent)
        self._name = name or server_name()
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept)
        self._buffers = {}

    def listen(self):
        # a socket left behind by a crashed lp-deck would block listening
        QLocalServer.removeServer(self._name)
        return self._server.listen(self._name)

    def close(self):
        self._server.close()

    def _accept(self):
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self._buffers[socket] = b""
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._finish(s))

    def _read(self, socket):
        if socket in self._buffers:
            self._buffers[socket] += bytes(socket.readAll())

    def _finish(self, socket):
        if socket not in self._buffers:
            return
        self._read(socket)
        data = self._buffers.pop(socket)
        # a socket being destroyed says "disconnected" again; don't hear it
        socket.readyRead.disconnect()
        socket.disconnected.disconnect()
        socket.deleteLater()
        try:
            paths = json.loads(data.decode() or "{}").get("open") or []
        except ValueError:
            return
        self.opened.emit([str(p) for p in paths])
