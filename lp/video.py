"""Render a whole album the way the kiosk plays it, to a video file.

The kiosk's now-playing frame is a pure function of (album, settings, time):
which track is on, how far the needle has travelled, how far the record has
turned. lp.shot renders one such frame headlessly; this walks every frame of
the album in order and pipes them into ffmpeg together with the album's audio.
The result is "that album, played on lp", ready for YouTube: a free whole-album
visualizer with the vinyl spinning and the needle tracking through the grooves.

    python -m lp.video "/music/Howling Giant/2025 - Crucible & Ruin" crucible.mp4
    python -m lp.video ALBUM out.mp4 --fps 60 --style nebula-teal-marble --effects glass
    python -m lp.video ALBUM out.mp4 --preview 20        # first 20 seconds, to check the look
    python -m lp.video ALBUM out.mp4 --codec h264        # if a player of yours lacks HEVC

Beside the video it writes ``<out>.txt``: the description for the upload, with
a timestamp per track. YouTube turns those into chapters, so the viewer gets a
track list for free. The same chapters are embedded in the MP4 itself.

Output is HEVC (H.265) in an MP4 with the ``hvc1`` tag (what Apple players
require), AAC audio at 320k. YouTube accepts HEVC uploads; use ``--codec h264``
for anything that does not. Frames are rendered at the kiosk's own rate (30
fps, the record turning 24 degrees a second) unless ``--fps`` says otherwise.

Needs ffmpeg on PATH. Rendering is offline, so a machine that cannot draw the
kiosk at full rate still produces a perfect video, just slower: expect a
45-minute album to take about half an hour at 1080p30 on a laptop.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lp.shot import add_look_arguments, album_info, headless_display, settings_from_args
from lpcore.vinyl.settings import VinylSettings

# The kiosk advances the record 0.8 degrees per frame at 30 fps. Time-based
# here, so any --fps gives the same spin.
RECORD_DEG_PER_SEC = 24.0
AUDIO_RATE = 48000

CODECS = {
    # crf: HEVC is more efficient, so a higher number lands at similar quality.
    'hevc': ['-c:v', 'libx265', '-preset', 'medium', '-crf', '22', '-tag:v', 'hvc1',
             '-x265-params', 'log-level=error'],
    'h264': ['-c:v', 'libx264', '-preset', 'medium', '-crf', '18'],
}


def _mmss(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


class AlbumPlan:
    """Everything the frames need to know about the album, and the text that
    goes with the upload. ``tracks`` is what lp.shot.album_info returns."""

    def __init__(self, tracks, cover=None, album_dir=None):
        if not tracks:
            raise ValueError('an album needs at least one track')
        self.tracks = tracks
        self.cover = cover
        self.album_dir = album_dir
        lengths = [t['length'] for t in tracks]
        self.boundaries = [sum(lengths[:i]) for i in range(len(tracks))]
        self.duration = sum(lengths)
        first = tracks[0]
        self.artist = first.get('artist') or ''
        self.album = first.get('album') or ''
        self.date = first.get('date') or ''

    @classmethod
    def from_folder(cls, folder):
        tracks, cover = album_info(folder)
        return cls(tracks, cover, folder)

    def track_at(self, t):
        """0-based index of the track playing at ``t`` seconds into the album."""
        index = 0
        for i, start in enumerate(self.boundaries):
            if t >= start:
                index = i
        return index

    def status(self, t):
        """The now-playing status dict Display._render_playing draws from."""
        i = self.track_at(t)
        return {
            'playing': True,
            'artist': self.artist,
            'album': self.album,
            'track_title': self.tracks[i]['title'],
            'track_number': i + 1,
            'total_tracks': len(self.tracks),
            'date': self.date,
            'progress': {
                'album_duration': self.duration,
                'elapsed': min(t, self.duration),
                'track_boundaries': self.boundaries,
            },
        }

    def title(self):
        year = self.date[:4] if len(self.date) >= 4 else ''
        head = ' - '.join(p for p in (self.artist, self.album) if p)
        return f'{head} ({year})' if year else head

    def description(self):
        """Upload description: title line, then a timestamp per track, which
        YouTube reads as chapters (the first one must be 00:00)."""
        lines = [self.title(), '', 'Played on lp: https://github.com/dkoch84/lp', '']
        for start, track in zip(self.boundaries, self.tracks):
            lines.append(f'{_mmss(start)} {track["title"]}')
        return '\n'.join(lines) + '\n'

    def ffmetadata(self):
        """Chapters in ffmpeg's metadata format, embedded in the MP4."""
        lines = [';FFMETADATA1', f'title={self.title()}', f'artist={self.artist}',
                 f'album={self.album}', '']
        for i, track in enumerate(self.tracks):
            start = self.boundaries[i]
            end = self.boundaries[i + 1] if i + 1 < len(self.tracks) else self.duration
            lines += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={int(start * 1000)}',
                      f'END={int(end * 1000)}', f'title={track["title"]}', '']
        return '\n'.join(lines)


def audio_command(track_paths, wav_out, ffmpeg='ffmpeg'):
    """Decode the album to one WAV, gapless. The concat *filter* (not the
    demuxer) is used so tracks in different formats or sample rates join
    cleanly; everything is resampled to AUDIO_RATE stereo."""
    cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y']
    for path in track_paths:
        cmd += ['-i', path]
    chain = ''.join(f'[{i}:a]' for i in range(len(track_paths)))
    cmd += ['-filter_complex', f'{chain}concat=n={len(track_paths)}:v=0:a=1[a]',
            '-map', '[a]', '-ar', str(AUDIO_RATE), '-ac', '2', '-c:a', 'pcm_s16le', wav_out]
    return cmd


def video_command(width, height, fps, wav, metadata, out, codec='hevc', ffmpeg='ffmpeg'):
    """Encode raw RGB frames from stdin with the WAV and chapters into ``out``."""
    if codec not in CODECS:
        raise ValueError(f'codec must be one of {", ".join(CODECS)}, not {codec!r}')
    return [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}',
            '-framerate', str(fps), '-i', '-',
            '-i', wav,
            '-i', metadata,
            '-map', '0:v', '-map', '1:a', '-map_metadata', '2',
            *CODECS[codec], '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '320k',
            '-movflags', '+faststart', out]


def wav_duration(path):
    with wave.open(path, 'rb') as w:
        return w.getnframes() / float(w.getframerate())


def render(plan, out, width=1920, height=1080, fps=30, settings=None, codec='hevc',
           seconds=None, ffmpeg='ffmpeg', log=print):
    """Render ``plan`` to ``out`` (and ``out`` + '.txt'). ``seconds`` caps the
    length, for previews. Returns the number of frames written."""
    if width % 2 or height % 2:
        raise ValueError('width and height must be even (yuv420p)')
    settings = settings or VinylSettings(label='art', label_text='none')
    paths = [t['path'] for t in plan.tracks]

    with tempfile.TemporaryDirectory(prefix='lp-video-') as tmp:
        wav = os.path.join(tmp, 'album.wav')
        log(f'  decoding {len(paths)} tracks to one gapless stream...')
        subprocess.run(audio_command(paths, wav, ffmpeg), check=True)
        duration = wav_duration(wav)
        if seconds is not None:
            duration = min(duration, float(seconds))
            trimmed = os.path.join(tmp, 'trim.wav')
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', wav,
                            '-t', str(duration), trimmed], check=True)
            wav = trimmed
        metadata = os.path.join(tmp, 'chapters.txt')
        with open(metadata, 'w') as f:
            f.write(plan.ffmetadata())

        pygame.init()
        display = headless_display(width, height, settings, plan.cover, plan.album_dir,
                                   title='lp-video')
        total_frames = int(math.ceil(duration * fps))
        log(f'  {plan.title()}: {_mmss(duration)}, {total_frames} frames at '
            f'{width}x{height}@{fps} ({codec})')

        proc = subprocess.Popen(video_command(width, height, fps, wav, metadata, out, codec,
                                              ffmpeg),
                                stdin=subprocess.PIPE)
        started = time.monotonic()
        surface = pygame.Surface((width, height))
        try:
            for frame in range(total_frames):
                t = frame / fps
                display._record_angle = (t * RECORD_DEG_PER_SEC) % 360.0
                display._render_playing(plan.status(t))
                display.renderer.present()
                display.renderer.to_surface(surface)
                proc.stdin.write(pygame.image.tobytes(surface, 'RGB'))
                if frame % (fps * 10) == 0 and frame:
                    rate = frame / (time.monotonic() - started)
                    eta = (total_frames - frame) / rate if rate else 0
                    log(f'  {_mmss(t)} / {_mmss(duration)}  {rate:.0f} fps, '
                        f'about {_mmss(eta)} to go')
        finally:
            proc.stdin.close()
            code = proc.wait()
        if code:
            raise RuntimeError(f'ffmpeg exited {code}')

    with open(out + '.txt', 'w') as f:
        f.write(plan.description())
    log(f'  wrote {out} and {out}.txt in {_mmss(time.monotonic() - started)}')
    return total_frames


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('album', help='an album folder (its tags, lengths and cover drive the video)')
    ap.add_argument('out', help='output .mp4')
    ap.add_argument('--size', default='1920x1080', help='resolution, WxH (default 1920x1080)')
    ap.add_argument('--fps', type=int, default=30, help='frame rate (default 30, the kiosk rate)')
    ap.add_argument('--codec', choices=sorted(CODECS), default='hevc',
                    help='video codec (default hevc; h264 for players without HEVC)')
    ap.add_argument('--preview', type=float, default=None, metavar='SECONDS',
                    help='render only the first SECONDS, to check the look')
    ap.add_argument('--ffmpeg', default='ffmpeg', help='ffmpeg binary (default: from PATH)')
    add_look_arguments(ap)
    args = ap.parse_args(argv)

    if not shutil.which(args.ffmpeg):
        print(f'{args.ffmpeg} not found; install ffmpeg', file=sys.stderr)
        return 2
    width, height = (int(v) for v in args.size.lower().split('x'))
    if not os.path.isdir(args.album):
        print(f'not a folder: {args.album}', file=sys.stderr)
        return 2
    try:
        plan = AlbumPlan.from_folder(args.album)
    except (SystemExit, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    render(plan, args.out, width, height, args.fps, settings_from_args(args), args.codec,
           seconds=args.preview, ffmpeg=args.ffmpeg)
    return 0


if __name__ == '__main__':
    sys.exit(main())
