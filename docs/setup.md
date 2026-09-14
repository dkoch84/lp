# Run from a checkout

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yml config.yml
# set music_library_path in config.yml
python main.py
```

The web UI is at `http://localhost:8000`. The record shows on whatever screen the process runs on.

A checkout does not update itself; `git pull` does that.

lp-deck and lp-studio need Qt on top:

```bash
pip install -r requirements-deck.txt
make deck      # lp-deck
make studio    # lp-studio
```

`make help` lists everything else. Run `make check` (lint and tests) before pushing.

## Your music

One folder per artist, one folder per album inside it:

```
Music/
  Howling Giant/
    2025 - Crucible & Ruin/
      01 Canyons.flac
      cover.jpg
```

A `2025 - ` in front of the album folder is shown as the year.

## Config

```yaml
music_library_path: /path/to/music

# VLC audio output: alsa (default), pulse, etc. Use pulse on a
# PipeWire or PulseAudio desktop so audio follows your default output.
# audio_output: alsa

display:
  fullscreen: false
  width: 1920
  height: 1080
  url: https://lp.example.com    # shown on the idle screen: where to open the web UI

api:
  host: 0.0.0.0
  port: 8000

# Self-update (release installs only; a checkout ignores this).
updates:
  auto: true
  check_hours: 6

# Optional, for Last.fm scrobbling. Sign in from the web UI afterwards.
lastfm:
  api_key: ""
  api_secret: ""
```
