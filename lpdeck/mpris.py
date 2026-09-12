"""MPRIS2 (D-Bus) media-key / desktop integration for lp-deck.

Standalone module: exposes the running lp-deck player on the session bus as an
``org.mpris.MediaPlayer2`` service so desktop media keys, KDE/GNOME media
applets, and tools like ``playerctl`` can drive playback and read now-playing
metadata.

Deliberately Qt-free — this only touches dbus-next, asyncio, threading, and the
stdlib. The dbus service runs in its own daemon thread with a private asyncio
event loop so it never blocks (or is blocked by) the Qt main loop. Player
callbacks fire on VLC/Qt threads, so every cross-thread touch of the loop goes
through ``loop.call_soon_threadsafe``.

Public API: ``start_mpris(player)`` — returns a handle with ``.stop()`` on
success, or ``None`` if MPRIS is unavailable (no dbus-next, no session bus,
headless, etc.). Callers treat ``None`` as "MPRIS off" and carry on.
"""

# dbus-next encodes D-Bus types as string annotations (``-> "x"``, ``-> "a{sv}"``,
# …). Ruff reads those as forward references and reports F821 "undefined name";
# they are the required dbus-next idiom, so suppress F821 (undefined name) and
# F722 (syntax error in forward annotation, e.g. ``"as"``/``"a{sv}"``) here.
# ruff: noqa: F821, F722

import asyncio
import logging
import threading
from pathlib import Path

log = logging.getLogger("lpdeck.mpris")

BUS_NAME = "org.mpris.MediaPlayer2.lpdeck"
OBJECT_PATH = "/org/mpris/MediaPlayer2"


def start_mpris(player):
    """Start the MPRIS2 D-Bus service for ``player`` in a background thread.

    Returns a handle object with a ``.stop()`` method on success, or ``None`` if
    MPRIS could not be started (dbus-next missing, no session bus, etc.).
    """
    try:
        from dbus_next import BusType, PropertyAccess, Variant
        from dbus_next.aio import MessageBus
        from dbus_next.service import (
            ServiceInterface,
            dbus_property,
            method,
            signal,
        )
    except Exception as e:  # pragma: no cover - import-environment dependent
        log.warning("MPRIS unavailable: dbus-next import failed: %s", e)
        return None

    # ------------------------------------------------------------------ helpers
    def _safe(fn, default=None):
        """Call a player/backend method, swallowing any backend hiccup so it
        never propagates into the dbus loop."""
        try:
            return fn()
        except Exception as e:
            log.debug("MPRIS: backend call failed: %s", e)
            return default

    # ----------------------------------------------------- root MediaPlayer2 iface
    class MediaPlayer2Interface(ServiceInterface):
        def __init__(self):
            super().__init__("org.mpris.MediaPlayer2")

        @method()
        def Raise(self):
            pass

        @method()
        def Quit(self):
            pass

        @dbus_property(access=PropertyAccess.READ)
        def CanQuit(self) -> "b":
            return False

        @dbus_property(access=PropertyAccess.READ)
        def CanRaise(self) -> "b":
            return False

        @dbus_property(access=PropertyAccess.READ)
        def HasTrackList(self) -> "b":
            return False

        @dbus_property(access=PropertyAccess.READ)
        def Identity(self) -> "s":
            return "lp-deck"

        @dbus_property(access=PropertyAccess.READ)
        def DesktopEntry(self) -> "s":
            return "lp-deck"

        @dbus_property(access=PropertyAccess.READ)
        def SupportedUriSchemes(self) -> "as":
            return ["file"]

        @dbus_property(access=PropertyAccess.READ)
        def SupportedMimeTypes(self) -> "as":
            return []

    # ---------------------------------------------------------- Player iface
    class PlayerInterface(ServiceInterface):
        def __init__(self):
            super().__init__("org.mpris.MediaPlayer2.Player")
            self._trackid_counter = 0

        # -- control methods -------------------------------------------------
        @method()
        def PlayPause(self):
            _safe(player.toggle)

        @method()
        def Play(self):
            _safe(lambda: player.backend.set_paused(False))

        @method()
        def Pause(self):
            _safe(lambda: player.backend.set_paused(True))

        @method()
        def Stop(self):
            _safe(player.backend.stop)

        @method()
        def Next(self):
            _safe(player.next)

        @method()
        def Previous(self):
            _safe(player.previous)

        @method()
        def Seek(self, offset: "x"):
            pass

        @method()
        def SetPosition(self, track_id: "o", position: "x"):
            pass

        @method()
        def OpenUri(self, uri: "s"):
            pass

        # -- helpers ---------------------------------------------------------
        def _playback_status(self) -> str:
            if _safe(player.backend.is_actively_playing, False):
                return "Playing"
            if _safe(player.current, None) is not None:
                return "Paused"
            return "Stopped"

        def _build_metadata(self) -> dict:
            cur = _safe(player.current, None)
            if not cur:
                return {}

            trackid = "/org/mpris/MediaPlayer2/lpdeck/track/%d" % self._trackid_counter
            meta = {"mpris:trackid": Variant("o", trackid)}

            title = cur.get("title")
            meta["xesam:title"] = Variant("s", title or "")

            artist = cur.get("artist")
            meta["xesam:artist"] = Variant("as", [artist] if artist else [])

            album_name = cur.get("album_name")
            meta["xesam:album"] = Variant("s", album_name or "")

            duration = cur.get("duration")
            if duration and duration > 0:
                meta["mpris:length"] = Variant("x", int(duration * 1_000_000))

            album_path = cur.get("album_path")
            if album_path:
                art = _safe(lambda: player.backend.find_album_art(album_path), None)
                if art:
                    try:
                        meta["mpris:artUrl"] = Variant("s", Path(art).as_uri())
                    except Exception as e:
                        log.debug("MPRIS: artUrl build failed: %s", e)

            return meta

        # -- properties ------------------------------------------------------
        @dbus_property(access=PropertyAccess.READ)
        def PlaybackStatus(self) -> "s":
            return self._playback_status()

        @dbus_property(access=PropertyAccess.READ)
        def LoopStatus(self) -> "s":
            return "None"

        @dbus_property(access=PropertyAccess.READ)
        def Rate(self) -> "d":
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def MinimumRate(self) -> "d":
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def MaximumRate(self) -> "d":
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def Shuffle(self) -> "b":
            return bool(getattr(player, "shuffle", False))

        @dbus_property(access=PropertyAccess.READWRITE)
        def Volume(self) -> "d":
            return _safe(lambda: player.backend.get_volume() / 100.0, 1.0)

        @Volume.setter
        def Volume(self, value: "d"):
            _safe(lambda: player.backend.set_volume(int(value * 100)))

        @dbus_property(access=PropertyAccess.READ)
        def Position(self) -> "x":
            return _safe(
                lambda: int(player.backend.get_current_time() * 1_000_000), 0
            )

        @dbus_property(access=PropertyAccess.READ)
        def Metadata(self) -> "a{sv}":
            return self._build_metadata()

        @dbus_property(access=PropertyAccess.READ)
        def CanGoNext(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanGoPrevious(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanPlay(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanPause(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanSeek(self) -> "b":
            return False

        @dbus_property(access=PropertyAccess.READ)
        def CanControl(self) -> "b":
            return True

        @signal()
        def Seeked(self, position: "x") -> "x":
            return position

        # -- live updates ----------------------------------------------------
        def _emit_changed(self):
            try:
                self.emit_properties_changed(
                    {
                        "PlaybackStatus": self._playback_status(),
                        "Metadata": self._build_metadata(),
                    }
                )
            except Exception as e:
                log.debug("MPRIS: emit_properties_changed failed: %s", e)

        def bump_track(self):
            self._trackid_counter += 1

    # ----------------------------------------------------- background runner
    class MprisService:
        def __init__(self):
            self.loop = asyncio.new_event_loop()
            self.thread = threading.Thread(
                target=self._run, name="lpdeck-mpris", daemon=True
            )
            self._bus = None
            self._player_iface = PlayerInterface()
            self._root_iface = MediaPlayer2Interface()
            self._ready = threading.Event()
            self._ok = False

        # called on the player/VLC/Qt thread -> marshal into the asyncio loop
        def _on_event(self, bump=False):
            def _apply():
                if bump:
                    self._player_iface.bump_track()
                self._player_iface._emit_changed()

            try:
                self.loop.call_soon_threadsafe(_apply)
            except Exception as e:
                log.debug("MPRIS: call_soon_threadsafe failed: %s", e)

        async def _setup(self):
            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
            self._bus.export(OBJECT_PATH, self._root_iface)
            self._bus.export(OBJECT_PATH, self._player_iface)
            await self._bus.request_name(BUS_NAME)

        def _run(self):
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self._setup())
                self._ok = True
            except Exception as e:
                log.warning("MPRIS unavailable: session bus setup failed: %s", e)
                self._ready.set()
                return
            self._ready.set()
            try:
                self.loop.run_forever()
            finally:
                try:
                    if self._bus is not None:
                        self._bus.disconnect()
                except Exception:
                    pass
                self.loop.close()

        def start(self):
            self.thread.start()
            self._ready.wait()
            if not self._ok:
                return False
            # Subscribe to backend events once the service is live. These fire
            # on a non-asyncio thread; _on_event marshals them onto the loop.
            try:
                player.backend.on("play_start", lambda: self._on_event(bump=False))
                player.backend.on("track_change", lambda: self._on_event(bump=True))
                player.backend.on("stop", lambda: self._on_event(bump=False))
            except Exception as e:
                log.debug("MPRIS: could not subscribe to backend events: %s", e)
            log.info("MPRIS service started (%s)", BUS_NAME)
            return True

        def stop(self):
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
            except Exception as e:
                log.debug("MPRIS: stop failed: %s", e)
            self.thread.join(timeout=2.0)

    service = MprisService()
    if not service.start():
        return None
    return service
