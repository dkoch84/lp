# lp Deployment

Two apps, one shared core (`lpcore`):

- **lp**: the album kiosk, a spinning-vinyl display window plus a web UI you
  control from any browser or phone on the LAN. Runs on a Linux box wired to a
  screen and speakers (an ODROID or Pi), or on any desktop.
- **lp-deck**: the desktop player (PySide6): full library, playlists, tracks,
  with the vinyl as the Now-Playing view.

There are two ways to have lp on a machine:

| | Release install | Git checkout |
|---|---|---|
| For | a kiosk or desktop that should just work | developing lp |
| Gets code from | GitHub Releases (tarball + rendered vinyl assets) | `git clone` |
| Updates | itself: periodic check, one tap in the web UI | `git pull`, `make prerender`, restart |
| Layout | `~/lp/releases/<tag>`, `~/lp/current` symlink | the checkout |
| Section | 1 | 2 |

Commands below are Debian/Ubuntu (`apt`); other distros use the equivalents.

## 1. Release install (kiosk or desktop)

### 1.1 System packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv curl vlc pipewire pipewire-pulse wireplumber
```

- `vlc` provides libVLC and the codecs `python-vlc` binds to.
- `pipewire` + `pipewire-pulse` is the audio server. It is what makes album
  playback gapless (section 3), so do not skip it.

### 1.2 Run the installer

```bash
curl -fsSL https://raw.githubusercontent.com/dkoch84/lp/master/deploy/install.sh | bash -s -- --music /path/to/music
```

It downloads the latest release and its rendered vinyl images into `~/lp`,
builds a virtualenv there, writes `~/.config/lp/config.yml`, and then:

- on a box with **no desktop** (no `DISPLAY`), installs a **systemd user
  service** so lp starts at boot and draws straight to the screen (kmsdrm);
- in a **desktop session**, installs an **app-menu entry** ("lp") that opens the
  vinyl window and the control UI in your browser.

Force either with `--kiosk` or `--desktop`. `--help` lists the rest.

The kiosk path needs two things only root can do. The installer prints them;
run them yourself:

```bash
sudo loginctl enable-linger <user>            # user services start at boot, no login needed
sudo usermod -aG video,render,audio <user>    # only if lp cannot open the screen or sound
```

Then:

```bash
systemctl --user start lp
journalctl --user -u lp -f
```

Nothing in the loop runs as root: the service is a user unit, and the updater
swaps a symlink in the user's home. That is deliberate: it is what lets the app
restart itself after an update without a sudo prompt anywhere.

### 1.3 Updates

lp checks GitHub for a new release every 6 hours (`updates.check_hours` in
config.yml). With `updates.auto: true` (the default) it downloads the release
and switches to it once the current album has finished. The web UI shows a
bar at the bottom either way: **Check now**, **Install now**, **After this
album**.

What an update does, in order: download the release tarball and only the
vinyl-cache families whose images changed (the manifest carries per-image
hashes), verify every checksum, unpack beside the running release, run pip
only if `requirements.txt` changed, flip `~/lp/current`, relaunch. The running
release is never modified; a failed download leaves it in place. The previous
release stays under `~/lp/releases/` for a manual rollback:

```bash
ln -sfn releases/<previous-tag> ~/lp/current && systemctl --user restart lp
```

From a shell, the same machinery:

```bash
~/lp/venv/bin/python -m lp.update status
~/lp/venv/bin/python -m lp.update check
~/lp/venv/bin/python -m lp.update install --restart
```

### 1.4 Where things live

```
~/lp/releases/<tag>/   one folder per installed release (RELEASE names it)
~/lp/current           symlink to the one that runs
~/lp/venv/             shared virtualenv
~/lp/cache/            rendered vinyl images (mandelbrot/, nebula/, munafo/), thumbnails
~/lp/data/             state: favorites, remembered port, Last.fm session + queue
~/.config/lp/config.yml
~/.config/systemd/user/lp.service          (kiosk)
~/.local/share/applications/lp.desktop     (desktop)
```

The service and desktop entry pass `LP_HOME`, `LP_CACHE_DIR` and `LP_DATA_DIR`
so the app finds all of it; see `lpcore/paths.py`.

### 1.5 Moving an old system-service install to this

Earlier kiosks ran a **system** unit (`/etc/systemd/system/lp.service`,
`User=<user>`) from a git checkout in `~/lp`. Move to the user service so the
updater can restart the app without root. When no album is playing:

```bash
sudo systemctl disable --now lp                  # the old system unit
sudo rm /etc/systemd/system/lp.service
sudo loginctl enable-linger <user>
mv ~/lp ~/lp-checkout                            # keep the checkout for development
curl -fsSL https://raw.githubusercontent.com/dkoch84/lp/master/deploy/install.sh | bash -s -- --kiosk
cp ~/lp-checkout/config.yml ~/.config/lp/config.yml     # or wherever it was
cp ~/lp-checkout/.lp_state.json ~/lp-checkout/.lastfm_session ~/lp/data/ 2>/dev/null
systemctl --user start lp
```

Check with `systemctl --user status lp` and `journalctl --user -u lp -f`. The
first boot after `enable-linger` is the real test: the user manager must come
up without a login, then pipewire, then lp.

## 2. Git checkout (development)

```bash
sudo apt install -y python3 python3-venv git vlc pipewire pipewire-pulse wireplumber
git clone https://github.com/dkoch84/lp.git ~/lp && cd ~/lp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.yml config.yml           # set music_library_path, audio_output: pulse
make run
```

`make` lists the rest (`deck`, `studio`, `shot`, `shot-kiosk`, `video`, `check`).
The kiosk updater sees a checkout as unmanaged and stays out of the way.

Update a checkout:

```bash
git pull && .venv/bin/pip install -r requirements.txt
```

## 3. Audio: pipewire, for gapless

On raw ALSA, VLC re-primes the output device at every track boundary and clips
the first fraction of the next track (a cut-off first word on continuous
albums). Routing through pipewire keeps one persistent stream across the whole
album, which fixes it.

```bash
systemctl --user enable --now pipewire pipewire-pulse wireplumber
# set  audio_output: pulse  in config.yml (the installer does this when it finds pipewire)
```

Volume: `wpctl set-volume @DEFAULT_AUDIO_SINK@ 100%`. Confirm lp connected:
the log line `play_album: ... aout=pulse` (not `alsa`).

On a headless kiosk the user's pipewire socket exists at boot only when
lingering is enabled for that user (`loginctl enable-linger`), which the
release install requires anyway.

## 4. Releasing

```bash
git tag crucible-and-ruin && git push origin crucible-and-ruin
```

The `Release` workflow packs the committed vinyl images per family with the
source tarball and a manifest, and attaches everything to the GitHub Release,
creating one with generated notes if you have not yet. Edit the notes on
GitHub afterwards. Add the release's title to `RELEASE_TITLES` in
`lpcore/version.py` first so the tag reads as a name in the UI.

Nothing is rendered in CI. `lpcore/cache/` is in git: after adding or retuning
a style, `make prerender` re-renders just that style (each image carries a key
derived from its parameters and the renderer code it reaches) and you commit
the image with the code. The workflow runs `prerender --check` and fails if a
committed style is stale, so a forgotten render never ships.

Build the same assets locally to inspect them: `make release-assets TAG=<tag>`.

## 5. lp-deck (desktop player)

Needs Qt on top of a checkout:

```bash
.venv/bin/pip install -r requirements-deck.txt
make deck
```
