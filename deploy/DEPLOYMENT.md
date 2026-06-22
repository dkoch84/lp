# lp Deployment

Two apps, one shared core (`lpcore`):

- **lp** — the album kiosk: a spinning-vinyl display window + a web UI you control
  from any browser/phone on the LAN. Runs on a Linux box wired to a screen and
  speakers (e.g. an ODROID/Pi), or on any desktop.
- **lp-deck** — the desktop player (PySide6): full library / playlists / tracks,
  with the vinyl as the Now-Playing view.

Paths below use `~/lp` for the checkout and `<user>` for your login — adjust to
taste. Commands are Debian/Ubuntu (`apt`); other distros use the equivalents.

## 1. System packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv git \
    vlc pipewire pipewire-pulse wireplumber
```

- `vlc` provides **libVLC + codecs** that `python-vlc` binds to (audio playback).
- `pipewire` + `pipewire-pulse` is the audio server — required for **gapless**
  (see step 4).

## 2. Clone + Python environment

```bash
git clone <repo-url> ~/lp && cd ~/lp
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## 3. Config

```bash
cp config.example.yml config.yml      # lp reads ./config.yml, or pass -c <path>
```

Edit it: set `music_library_path` (a local folder or an NFS/SMB mount), the
display size, and **`audio_output: pulse`** (for gapless — step 4). The control
port defaults to a remembered random one; set `api.port` to pin it (e.g. behind
a proxy).

## 4. Audio — pipewire (for gapless)

On raw ALSA, VLC re-primes the output device at every track boundary and clips
the first fraction of the next track (audible as a cut-off first word on
continuous albums). Routing through pipewire keeps **one persistent stream**
across the whole album, which fixes it. (lp also passes `--no-audio-time-stretch`
to VLC, which helps on ALSA but isn't a full fix on its own.)

Start the user audio services and point lp at them:

```bash
systemctl --user enable --now pipewire pipewire-pulse wireplumber
# set  audio_output: pulse  in config.yml
```

Volume: `wpctl set-volume @DEFAULT_AUDIO_SINK@ 100%`. Confirm lp connected — the
log line `play_album: … aout=pulse` (not `alsa`).

**Headless kiosk note:** if lp runs as a *system* service (no graphical login),
the user pipewire socket won't exist at boot and the service can't see it. Fix:

```bash
sudo loginctl enable-linger <user>     # user services start at boot
# add to the lp unit:  Environment=XDG_RUNTIME_DIR=/run/user/$(id -u <user>)
```

## 5. Run the kiosk (lp)

Foreground (opens the vinyl window, prints the control URL, opens a browser at a
desktop):

```bash
venv/bin/python main.py
```

Autostart as a service — edit `deploy/lp.service` (`User`, `WorkingDirectory`,
the `ExecStart` config path), then:

```bash
sudo cp deploy/lp.service /etc/systemd/system/
sudo systemctl enable --now lp
journalctl -u lp -f
```

The web UI is on the config'd port; reach it from any device on the LAN. To
expose it beyond the LAN, put a reverse proxy (e.g. nginx) in front, forwarding
to `http://<host>:<port>`.

## 6. Run the desktop (lp-deck)

Needs Qt on top of the same checkout:

```bash
venv/bin/pip install PySide6
venv/bin/python -m lpdeck
```

## Update

```bash
cd ~/lp && git pull && venv/bin/pip install -r requirements.txt
sudo systemctl restart lp        # if running as a service
```
