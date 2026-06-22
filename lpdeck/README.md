# lp-deck

A full desktop music player (PySide6) built on `lpcore`, with the lp spinning
vinyl as the Now-Playing view. Sibling to the `lp` kiosk; both share `lpcore`
(player, library, scrobbler, vinyl renderer). **`lpcore`/`lp` never import Qt;
PySide6 lives only here.**

## Run

```bash
.venv/bin/pip install PySide6        # not yet a venv dep (system has 6.11)
.venv/bin/python -m lpdeck
```

## Architecture

```
lpdeck/
├── __main__.py     entry — wires config + SQLite + lpcore + Qt
├── app.py          MainWindow: nav (Artists/Playlists/Queue) + search + now-playing
├── db.py           SQLite: library index, playlists, vinyl overrides   ✓ testable
├── vinyl_widget.py VinylWidget — lpcore VinylRenderer surfaces, spun in Qt
├── player.py       QueuePlayer — track-level queue over lpcore.PlayerBackend
└── indexer.py      library scan (lpcore.library + mutagen) → SQLite     [TODO]
```

Reused from `lpcore`: `PlayerBackend` (gapless VLC), `Library` scan, `Scrobbler`,
and the whole `vinyl` package (`VinylRenderer`, `VinylSettings`, catalog, fractals).

## Requirements → status

| # | Requirement | Status |
|---|---|---|
| 1 | Views: Artists → Albums/Songs, Playlists | nav + stacked views scaffolded; view bodies TODO |
| 2 | "Open in MusicBrainz Picard" + manual Edit Metadata (user picks) | TODO — context-menu: launch `picard <paths>`; manual tag editor via mutagen |
| 3 | Queue | `QueuePlayer` model in place; **needs lpcore `play_tracks`** |
| 4 | Search (artists/albums/songs) | search box wired; query TODO |
| 5 | Filters & sorts | per-view, TODO |
| 6 | Now-playing = LP vinyl + album art | **`VinylWidget` done** (drives lpcore renderer) |
| 7 | Vinyl config: global default, per-artist, per-album override | **storage + resolution done** (`db.resolve_vinyl_settings`); UI selector stubbed |
| 8 | SQLite storage | **`db.py` schema done** |
| 9 | LastFM scrobbling | reuses `lpcore.Scrobbler` (wired in `__main__`) |

## Next steps (in order)

1. **`lpcore.PlayerBackend.play_tracks(files, album_path=None)`** — generalise
   `play_album` to an explicit file list (small, benefits the queue). Then wire
   `QueuePlayer` to it.
2. **`indexer.py`** — populate SQLite from the library (track-level via mutagen),
   incremental by mtime.
3. **Library view** — Artists → Albums → Songs, fed from SQLite; double-click →
   set queue. Then Playlists, Queue, Search, Filters/Sorts.
4. **Picard / metadata** (req #2) — right-click → "Open in MusicBrainz Picard"
   (`subprocess` launch) or "Edit Metadata" (manual mutagen tag form).
5. **Vinyl override UI** (req #7) — the now-playing scope selector writes
   `db.set_vinyl_override`; `VinylWidget.set_settings` on resolve.
