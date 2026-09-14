# Architecture

Built to run on a small Linux board (a Raspberry Pi or an Odroid) plugged into a TV. The web UI is the remote.

```
main.py        the kiosk: starts the player, the display and the web server
lpcore/        shared by everything; never imports Qt
  player.py      VLC playback, gapless
  library.py     scans Artist/Album folders
  scrobbler.py   Last.fm
  vinyl/         the record: styles, renderer, effects, prerender
  cache/         the rendered style images, committed
lp/            the kiosk
  display.py     the pygame window
  api.py         the FastAPI server behind the web UI
  looks.py       saved looks, for every album and per album
  queue.py       albums queued with Play next
  state.py       favorites and recently played
  update.py      the self-updater (standard library only)
  release.py     builds the release assets
  video.py       album videos
  shot.py        headless screenshots
lpdeck/        lp-deck, the Qt desktop player
lpstudio/      lp-studio, the Qt style editor
static/        the web UI
deploy/        install script, service unit, deployment guide
tests/
```

`lpcore` and `lp` never import Qt, so the kiosk runs without it. Only lp-deck and lp-studio need Qt.

Just play the damn record.
