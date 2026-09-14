# Album video

```bash
make video ALBUM="/music/Howling Giant/2025 - Crucible & Ruin" OUT=crucible.mp4
```

Renders the whole album the way the kiosk plays it: the record spinning, the needle tracking through the grooves, and the album's audio joined without gaps. The result is a 1080p HEVC MP4.

Next to it you get a `.txt` with a YouTube description: one timestamp per track, which YouTube turns into chapters. A free whole-album visualizer for any band.

It takes a few minutes with a hardware encoder (NVENC, VideoToolbox, QuickSync and AMF are picked up by themselves), longer without one. Needs ffmpeg.

Options (pass them as `ARGS="..."` to `make video`, or call `python -m lp.video` directly):

- `--preview 20`: only the first 20 seconds, to check the look
- `--codec h264`: for players without HEVC
- `--size 1280x720`, `--fps 30`
- `--style`, `--label`, `--label-text`, `--effects`, `--grooves`, `--frame-color`, `--panel-color`: the same values the web UI's vinyl page uses

lp-deck has the same thing as a **Video…** button on every album page.
