# lp-deck

A full desktop music player (PySide6) built on `lpcore`, with the lp spinning
vinyl as the Now-Playing view. Sibling to the `lp` kiosk; both share `lpcore`
(player, library, scrobbler, vinyl renderer). **`lpcore`/`lp` never import Qt;
PySide6 lives only here.**

## Run

```bash
.venv/bin/python -m lpdeck           # PySide6 6.11 already in the venv (incl. QtQuick)
# or: make deck
```

## Debugging the UI

QML has no browser-style devtools, but a few things make iteration fast:

- **`make shot`** (`python -m lpdeck.shot out.png [--play --expand --vinyl --queue]`)
  renders the real `Main.qml` to a PNG headlessly (offscreen, fake now-playing
  state) and prints QML warnings with teardown GC noise filtered. This is the
  fastest way to eyeball a layout/popup/the vinyl without a display.
- **GammaRay** (`make gammaray`, needs `gammaray` installed) is the real Qt
  equivalent of devtools: live object tree, property/binding inspector, the QML
  scene graph, signal monitor. Inspects a running `python -m lpdeck`.
- **Env vars** for a live run: `QSG_VISUALIZE=overdraw|batches|clip`,
  `QML_IMPORT_TRACE=1`, `QT_LOGGING_RULES="qt.quick.*=true"`.
- QML warnings print to stderr in a normal run. The recurring "Cannot read
  property … of null" lines only appear at process teardown (context object GC'd
  before the bindings) and are harmless — `shot.py` filters them out.

## Architecture

The view layer is **Qt Quick (QML)** — GPU scene graph, so the artist grid
scrolls/scales smoothly (QWidgets icon views reflowed on the CPU and were janky).
Python stays the backend; QML is fed by a model + a tile image-provider.

```
lpdeck/
├── __main__.py     entry — wires config + SQLite + lpcore, launches qmlapp
├── qmlapp.py       QML host: TileProvider (off-thread art), ArtistsModel,
│                   Controller (search / drill-down / playback / now-playing)
├── qml/Main.qml    window: sidebar + search → artist grid → album grid → song table + now-playing
├── qml/Theme.qml   dark theme tokens (charcoal + vinyl-amber accent)
│                   (TileProvider disk-caches rendered art → ~/.cache/lp-deck/tiles)
├── db.py           SQLite: library index, playlists, vinyl overrides   ✓ testable
├── mosaic.py       artist/album tile rendering (QImage; off-thread safe)
├── vinyl_item.py   VinylItem — QQuickPaintedItem spinning lpcore's VinylRenderer
├── vinyl_preview.py static vinyl swatches for the override chooser (disc-cached)
├── meta.py         track tag read/write via mutagen (Edit-Metadata form)
├── player.py       QueuePlayer — track-level queue over lpcore.PlayerBackend
└── indexer.py      library scan (lpcore.library + mutagen) → SQLite
```

The legacy QWidgets prototype (`app.py`, `library_view.py`, `queue_panel.py`,
`theme.py`, `vinyl_widget.py`) has been removed — the QML view fully replaces it.

Reused from `lpcore`: `PlayerBackend` (gapless VLC), `Library` scan, `Scrobbler`,
and the whole `vinyl` package (`VinylRenderer`, `VinylSettings`, catalog, fractals).

## Requirements → status

| # | Requirement | Status |
|---|---|---|
| 1 | Views: Artists → Albums/Songs, Playlists | **Done** — sidebar nav + 3-level drill (Artists → albums → song table → play). Song rows: left-click plays, **right-click** = action sheet, hover checkbox = multi-select. **Playlists**: create, add one/many songs / a whole album / an artist (right-click or ＋), **drag-reorder** (`movePlaylistTrack`); each track keeps its album so now-playing art + vinyl + expand follow the current track (`playPlaylist`). |
| 2 | "Open in MusicBrainz Picard" + manual Edit Metadata (user picks) | **Done** — per-track ⋯ action sheet: "Open in MusicBrainz Picard" (`subprocess`, `meta`-less) + "Edit metadata" form (mutagen via `meta.py`, re-indexes the row) |
| 3 | Queue | **QML collapsible queue panel** (`QueueModel` + `☰` toggle by the transport): rows + ▶ marker, click-to-jump (`jumpTo`→`QueuePlayer.jump_to`), live "N/M remaining, time remaining/total" footer (1 s ticker) |
| 4 | Search (artists/albums/songs) | **Done** — search field → results page with Artists / Albums / Songs sections (`Controller.search`); click to drill or play |
| 5 | Filters & sorts | **Settings popup (⚙)**: light/dark theme, artist sort (name ↑/↓), album sort (year/name), grid item size (S/M/L); persisted via `QSettings`. Grid auto-fits columns to window width. Now-playing header + expanded view use an **album-art-tinted gradient** (`Controller.npAccent`). Per-view filters still TODO |
| 6 | Now-playing = LP vinyl + album art | **Compact top header** (Elisa-style: album art + flat transport + seek bar) with a ⛶ **expand** button → full-app takeover in the **lp-kiosk layout** (album art left, spinning `VinylItem` right). Spin matches lp's `display.py` (0.8°/frame @ 30fps). NB: bind the VinylItem via `win.appController`, not the bare `controller` (its own `controller` property self-shadows). |
| 7 | Vinyl config: global default, per-artist, per-album override | **Done** — ◉ opens a **full-screen vinyl config** (takes over the main area; Now-Playing header + queue stay): scope (album/artist/global) + the **full sectioned catalog** as large rendered disc swatches (Basic / Coloured / Mandelbrot / Nebula / Munafo — 149 named variants, mirrors lp's web picker via `Controller.vinylCatalog`) + label colours → `Controller.setVinyl` → `db.set_vinyl_override`; `VinylItem` re-renders live. Previews via `image://vinyl/<style>~<label>` (disk-cached, composited through `composite_disc` so grooves match lp); fractal families need the `lpcore/cache` prerender (`fractals.prerender_all`). |
| 8 | SQLite storage | **`db.py` schema done** |
| 9 | LastFM scrobbling | reuses `lpcore.Scrobbler` (wired in `__main__`) |

## Status

All nine requirements are implemented. The QML view covers: sidebar nav, 3-level
drill (artists → albums → song table), search, playlists (create / add / play),
collapsible queue panel, per-track metadata + Picard, settings (sort + grid
size), disk-cached art, the spinning vinyl now-playing, and per-scope vinyl
overrides.

## Beyond the nine — standard-player features

The transport and library now carry what most desktop players have:

| Area | Feature |
|------|---------|
| Transport | **Seek** (click/drag the queue-wide bar → `controller.seek`), **volume** + mute, **shuffle**, **repeat** off/all/one, play/pause icon reflects real state |
| Queue | **Add to queue** / **Play next** (`queueAlbum`/`queueTracks` → live `append_tracks`/`insert_tracks_next`, no playback interruption) |
| Library | **♥ Favourites**, **Recently played**, **Most played**, **Recently added** smart lists; **Genres** browser; play-count + history tracking (`play_history`) |
| Tracks | Per-track favourite toggle + rating; row sheet adds Play-next / Add-to-queue / Favourite / Remove-from-playlist |
| Playlists | **Rename** + **delete** (right-click), **remove track**, existing drag-reorder |
| Formats | mp3/flac **plus** m4a/aac, ogg/opus, wav, wma, aiff (generic mutagen path) |
| Session | **Resume on launch** — queue + position saved to `session.json`, restored paused |
| Desktop | **MPRIS2 / D-Bus** (`mpris.py`, dbus-next) — media keys, lock-screen/notification controls, `playerctl`; degrades to no-op if no session bus |
| Lyrics | **Synced lyrics** in the expanded view (♫ toggle): sibling `.lrc` (synced, auto-scrolls + highlights the active line), embedded USLT/SYLT/Vorbis/MP4 tags, or `.txt` — `lpcore/lyrics.py` |
| Audio | **Equalizer** (live, 8 preset curves + preamp), **Crossfade** (0–12 s two-player overlap engine), **ReplayGain** volume normalisation (track/album, instance-level → applies on restart) |
| Expanded view | Full transport mirrored into the full-screen now-playing: shuffle/repeat/seek/volume/favourite + lyrics + vinyl toggles |

`mpris.py` is Qt-free and optional (graceful `None` if dbus-next/bus is absent).
EQ uses our own preset curves because `vlc.AudioEqualizer(i)` is not a preset
constructor: python-vlc treats a lone int as a raw C pointer, so index `0`
yields `None` and any other index yields an object pointing at that memory
address, which segfaults on first use. The working preset API is the
module-level `vlc.libvlc_audio_equalizer_new_from_preset(i)`. See
`lpcore.player.set_equalizer` and the canaries in `tests/test_player_eq.py`.
Crossfade routes through a manual two-player engine (`_play_crossfade`) since
the gapless list player has no overlap; crossfade `0` keeps the pure gapless
path. The lyrics parser is unit-tested (`tests/test_lyrics.py`, 14 cases).

Possible polish (not blocking): per-view filters beyond sort, live re-query of the
now-open song table after an external reindex, richer vinyl controls
(brightness/decor/label-text), online lyric/art fetch, sleep timer.
