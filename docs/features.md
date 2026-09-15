# Features

## The kiosk

- Plays whole albums, gapless, through libVLC.
- A spinning record with a needle that follows the grooves; each track is its own band of grooves.
- Now playing: artist, album, year, track number and title.
- Lots of vinyl styles: see [vinyl styles](vinyl-styles.md).
- The look is saved, so a restart keeps it, and an album can keep a look of its own.
- Updates itself from GitHub releases: see [install](install.md).
- Renders an album as a video: see [album video](album-video.md).

## The web UI

- Your phone is the remote. Browse artists, tap an album, it plays.
- Search and sort artists, and star your favorites.
- A record that is on is not cut off by a stray tap: lp asks first, and **Play next** queues the album for when this one ends.
- Recently played counts an album once a song of it has finished, so mis-taps never land there. Remove anything with its corner x.
- The vinyl page: style, label, label text, effects, grooves, brightness and colours, for every album or just the one playing. Star styles to show only those.
- The release name at the top shows what you have and installs new releases.
- Take a screenshot of the kiosk screen.

## Scrobbling

- Last.fm: add `api_key` and `api_secret` to `config.yml`, then sign in from the web UI.
- Paused time doesn't count toward a scrobble.
- Scrobbles made while offline are kept and sent once Last.fm is reachable again.

## lp-deck

- A full desktop player: artists, albums, tracks, genres, playlists and search.
- Smart lists: favourites, recently played, most played, recently added.
- A queue with play next and add to queue, restored when you start it again.
- Synced lyrics, an equalizer, crossfade and ReplayGain.
- Media keys and desktop controls (MPRIS).
- The spinning record as the now playing view, with a vinyl per album, per artist, or for everything.
- A **Video…** button on every album page.

More in [lpdeck/README.md](../lpdeck/README.md).

## lp-studio

- Design vinyl styles with sliders and a live spinning preview.
- Families: mandelbrot, color, nebula, clouds, smoke, black, clear.
- Smoke colours link to the light colour at teal-marble's brightness steps, with warnings when a style will look flat on a big screen.
- Colour variations: the same smoke turned round the colour wheel, one click to try each.
- Compare against every shipped style in the family, side by side.
- Undo and redo for every change, a filter for the controls, dark and light themes.
- Save your work as a template. Ship a smoke, clouds or nebula style as a style file with its image rendered; export a snippet for mandelbrot and colour styles.
