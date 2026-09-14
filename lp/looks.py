"""What the kiosk's vinyl looks like: one look for everything, and a look an
album can keep for itself.

The web UI's vinyl page edits the look that is on screen. Before this it
edited a single in-memory VinylSettings, so a restart (an update, a reboot)
quietly put every choice back to the defaults, and there was no way to say
"this record is teal-marble, the rest are whatever". Now:

  * the global look and every per-album look are saved in the data folder
    (``.lp_looks.json``) the moment they change;
  * the effective look, the VinylSettings object the display reads, is the
    defaults, then the global look, then the playing album's look on top;
  * an edit carries a scope: ``global`` (all albums) or ``album`` (the one
    playing now), and the album scope starts from what is on screen, so
    "keep this for this album" is one tap away.

The player's play_start and stop events keep ``current`` (the album path)
in step, and the display's texture caches key on the settings, so a swap
redraws by itself.
"""
import json
import logging
import os
import threading

from lpcore.vinyl.settings import VinylSettings

log = logging.getLogger('lp.looks')

SCOPES = ('global', 'album')


class Looks:
    def __init__(self, path=None, effective=None, player=None):
        self.path = path
        self.effective = effective if effective is not None else VinylSettings()
        self.player = player
        self.global_look = {}
        self.album_looks = {}
        self.current = None
        self._lock = threading.Lock()
        if not self._load():
            # Nothing saved yet: whatever the app constructed the settings
            # with IS the look, so adopt it rather than reset to defaults.
            defaults = VinylSettings().to_dict()
            self.global_look = {k: v for k, v in self.effective.to_dict().items()
                                if v != defaults[k]}
        self._apply()
        if player is not None and hasattr(player, 'on'):
            player.on('play_start', self.sync)
            player.on('stop', self.sync)

    # --- persistence --------------------------------------------------------

    def _load(self):
        """Read the saved looks; True when a file was read."""
        if not self.path or not os.path.isfile(self.path):
            return False
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            log.warning('looks: could not read %s: %s', self.path, e)
            return False
        self.global_look = self._clean(data.get('global', {}))
        self.album_looks = {p: self._clean(look) for p, look in data.get('albums', {}).items()
                            if look}
        return True

    @staticmethod
    def _clean(look):
        """Keep only fields VinylSettings knows, with values it accepts."""
        out = {}
        probe = VinylSettings()
        for key, value in (look or {}).items():
            if not hasattr(probe, key):
                continue
            try:
                probe.update(**{key: value})
            except ValueError:
                continue
            out[key] = value
        return out

    def _save(self):
        if not self.path:
            return
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'global': self.global_look, 'albums': self.album_looks}, f, indent=1,
                      sort_keys=True)
        os.replace(tmp, self.path)

    # --- the effective look -------------------------------------------------

    def _apply(self):
        look = VinylSettings().to_dict()
        look.update(self.global_look)
        if self.current:
            look.update(self.album_looks.get(self.current, {}))
        self.effective.update(**look)

    def set_album(self, path):
        with self._lock:
            self.current = path or None
            self._apply()

    def sync(self):
        """Follow the player: the album that is on, or none."""
        player = self.player
        if player is None:
            return
        try:
            playing = bool(player.get_status().get('playing'))
            path = getattr(player, 'album_path', None) if playing else None
        except Exception:
            path = None
        self.set_album(path)

    # --- edits ----------------------------------------------------------------

    def update(self, scope='global', **changes):
        """Apply ``changes`` at ``scope``. Values of None are skipped. Raises
        ValueError for a bad value, an unknown scope, or the album scope with
        nothing playing. Nothing is applied when any value is bad."""
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}, not {scope!r}")
        changes = {k: v for k, v in changes.items() if v is not None}
        probe = VinylSettings()
        probe.update(**changes)                       # validates every key first
        canonical = {k: getattr(probe, k) for k in changes}
        with self._lock:
            if scope == 'album':
                if not self.current:
                    raise ValueError('nothing is playing, so there is no album to keep a look for')
                if self.current not in self.album_looks:
                    # Start from what is on screen, so the album keeps its
                    # whole look, not just the one field being changed.
                    self.album_looks[self.current] = self.effective.to_dict()
                self.album_looks[self.current].update(canonical)
            else:
                self.global_look.update(canonical)
            self._apply()
            self._save()
        return self.effective

    def forget_album(self, path=None):
        """Drop an album's own look (the playing album by default). Returns
        True if there was one."""
        with self._lock:
            path = path or self.current
            had = self.album_looks.pop(path, None) is not None if path else False
            if had:
                self._apply()
                self._save()
            return had

    def status(self):
        with self._lock:
            return {
                'scopes': list(SCOPES),
                'album': self.current,
                'album_has_look': bool(self.current and self.current in self.album_looks),
                'albums_with_looks': len(self.album_looks),
            }
