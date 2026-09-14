"""Render a whole album the way the kiosk plays it, to a video file.

The kiosk's now-playing frame is a pure function of (album, settings, time):
which track is on, how far the needle has travelled, how far the record has
turned. Nearly all of it is static for a whole track, so this does not draw
frames one by one. It renders each layer once with the real kiosk code and
hands them to ffmpeg to composite:

    background, one per track    the art, the panel and the text, from
                                 Display._render_playing with the record off
    the spin                     one revolution of the record (body, grooves
                                 and the fixed shine, drawn by the kiosk
                                 renderer at every angle it would show), as
                                 a short lossless clip that loops
    the tonearm                  one small image per pixel of needle travel,
                                 fed at the rate the needle actually moves

so the whole album encodes as fast as the encoder allows: a few minutes with
a hardware HEVC encoder (NVENC, VideoToolbox, QuickSync), rather than the
hour-plus that drawing 85,000 frames in Python and feeding libx265 took.
Every look option (style, label, label text, effects, grooves, colours)
applies exactly as on the kiosk; it is set once per render. The record
turns 24 degrees a second, so a revolution is exactly 15 seconds at any
frame rate, which is why the spin clip loops seamlessly.

    python -m lp.video "/music/Howling Giant/2025 - Crucible & Ruin" crucible.mp4
    python -m lp.video ALBUM out.mp4 --fps 60 --style nebula-teal-marble --effects glass
    python -m lp.video ALBUM out.mp4 --preview 20        # first 20 seconds, to check the look
    python -m lp.video ALBUM out.mp4 --codec h264        # if a player of yours lacks HEVC

Beside the video it writes ``<out>.txt``: the description for the upload, with
a timestamp per track. YouTube turns those into chapters, so the viewer gets a
track list for free. The same chapters are embedded in the MP4 itself.

Output is HEVC (H.265) in an MP4 with the ``hvc1`` tag (what Apple players
require), AAC audio at 320k. YouTube accepts HEVC uploads; use ``--codec h264``
for anything that does not. Needs ffmpeg on PATH.
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

from lp.display import NEEDLE_COLOR, TONEARM_COLOR, tonearm_points
from lp.shot import add_look_arguments, album_info, headless_display, settings_from_args
from lpcore.vinyl.catalog import INNER_GROOVE, OUTER_GROOVE
from lpcore.vinyl.settings import VinylSettings

# The kiosk advances the record 0.8 degrees per frame at 30 fps. Time-based
# here, so any --fps gives the same spin.
RECORD_DEG_PER_SEC = 24.0
AUDIO_RATE = 48000

# Encoders in order of preference per codec. Hardware first: a laptop GPU
# does HEVC at ten times realtime where libx265 manages one or two. Each is
# probed with a one-frame encode using these exact arguments, since being
# listed does not mean usable.
#
# B-frames are off everywhere. On a slowly turning, high-detail record the
# P-frames come out visibly sharper than the B-frames between them, and that
# 7.5 Hz sharp/soft pulse reads as jitter (measured: the frame-to-frame
# sharpness swing halves with -bf 0, at the same speed and about a quarter
# more bitrate, which an upload can afford).
ENCODERS = {
    'hevc': [
        ('hevc_nvenc', ['-preset', 'p4', '-rc', 'vbr', '-cq', '24', '-b:v', '0', '-bf', '0',
                        '-tag:v', 'hvc1']),
        ('hevc_videotoolbox', ['-q:v', '60', '-tag:v', 'hvc1']),
        ('hevc_qsv', ['-global_quality', '24', '-bf', '0', '-tag:v', 'hvc1']),
        ('hevc_amf', ['-quality', 'quality', '-rc', 'cqp', '-qp_i', '24', '-qp_p', '24', '-bf', '0',
                      '-tag:v', 'hvc1']),
        # Software HEVC is the slow path (about 2x realtime at 1080p on a
        # fast laptop); superfast at crf 22 is fine for an upload YouTube
        # re-encodes anyway.
        ('libx265', ['-preset', 'superfast', '-crf', '22', '-tag:v', 'hvc1',
                     '-x265-params', 'log-level=error:bframes=0']),
    ],
    'h264': [
        ('h264_nvenc', ['-preset', 'p4', '-rc', 'vbr', '-cq', '21', '-b:v', '0', '-bf', '0']),
        ('h264_videotoolbox', ['-q:v', '65']),
        ('libx264', ['-preset', 'medium', '-crf', '18', '-bf', '0']),
    ],
}
_probed = {}


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


def encoder_works(name, ffmpeg='ffmpeg', args=(), size=(256, 144)):
    """True when ffmpeg can actually encode a frame with ``name`` and ``args``
    at ``size``. The size matters: hardware encoders have a minimum frame
    size (AMF refuses 160x90 though 256x144 passes)."""
    key = (ffmpeg, name, tuple(args), tuple(size))
    if key not in _probed:
        r = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                            '-i', f'color=size={size[0]}x{size[1]}:rate=30', '-frames:v', '2',
                            '-c:v', name, *args, '-f', 'null', '-'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _probed[key] = r.returncode == 0
    return _probed[key]


def pick_encoder(codec='hevc', ffmpeg='ffmpeg', size=(1920, 1080)):
    """(encoder name, its arguments) for ``codec``: the first that works at
    ``size``."""
    if codec not in ENCODERS:
        raise ValueError(f'codec must be one of {", ".join(ENCODERS)}, not {codec!r}')
    for name, args in ENCODERS[codec]:
        if encoder_works(name, ffmpeg, args, size):
            return name, list(args)
    raise RuntimeError(f'ffmpeg has no working {codec} encoder')


def segment_frames(seconds_list, fps):
    """Whole-frame lengths for consecutive segments whose boundaries stay
    within half a frame of the cumulative real times."""
    frames, total = [], 0
    acc = 0.0
    for seconds in seconds_list:
        acc += seconds
        n = max(1, round(acc * fps) - total)
        frames.append(n)
        total += n
    return frames


def compose_command(width, height, fps, backgrounds, spin, arm, wav, metadata, out,
                    encoder, duration, ffmpeg='ffmpeg'):
    """The one ffmpeg run that makes the video.

    ``backgrounds`` is [(png, seconds)] in track order; ``spin`` is (clip,
    x, y), one revolution of the record to loop at the record's rect; ``arm``
    is (pattern, frames_per_second, x, y) for the tonearm image sequence;
    ``encoder`` is (name, args) from pick_encoder.

    Stills are decoded once and repeated with the loop filter, and every
    input is converted to the output's yuv420 family up front, so the
    per-frame work is two overlays on frames that need no conversion. (An
    image input with ``-loop 1`` re-decodes the PNG every frame, and overlay
    silently converts any RGB input each frame; both cost more than the
    encode.)
    """
    name, enc_args = encoder
    cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostats', '-progress', 'pipe:1', '-y']
    for png, _seconds in backgrounds:
        cmd += ['-framerate', str(fps), '-i', png]
    n = len(backgrounds)
    clip, sx, sy = spin
    cmd += ['-stream_loop', '-1', '-i', clip]
    pattern, rate, ax, ay = arm
    cmd += ['-framerate', f'{rate:.9f}', '-i', pattern]
    cmd += ['-i', wav, '-i', metadata]
    i_spin, i_arm, i_wav, i_meta = n, n + 1, n + 2, n + 3

    # Each segment is cut at a whole number of frames, rounding carried so a
    # boundary is never more than half a frame from the tagged one. A cut
    # at a fractional time (track lengths always are) lands the next segment
    # off the frame grid, and the record overlay then repeats every third
    # frame for the rest of that track.
    parts = []
    for i, frames in enumerate(segment_frames([sec for _p, sec in backgrounds], fps)):
        parts.append(f'[{i}:v]format=yuv420p,loop=loop=-1:size=1,'
                     f'trim=end_frame={frames},setpts=PTS-STARTPTS[g{i}]')
    # settb: concat hands out microsecond timestamps, so 1/fps steps are
    # rounded, while the spin clip's are exact. From the first segment that
    # starts on a rounded value the overlay falls a frame behind every third
    # frame (the record visibly stuttered for all of track 2 and beyond).
    # An exact 1/fps timebase on the main stream keeps the two in lockstep.
    parts.append(''.join(f'[g{i}]' for i in range(n))
                 + f'concat=n={n}:v=1:a=0,settb=1/{fps}[bg]')
    parts.append(f'[{i_arm}:v]format=yuva420p[arm]')
    parts.append(f'[bg][{i_spin}:v]overlay=x={sx}:y={sy}:eof_action=repeat[b1];'
                 f'[b1][arm]overlay=x={ax}:y={ay}:eof_action=repeat,fps={fps},format=yuv420p[v]')
    cmd += ['-filter_complex', ';'.join(parts), '-map', '[v]', '-map', f'{i_wav}:a',
            '-map_metadata', str(i_meta),
            '-c:v', name, *enc_args, '-c:a', 'aac', '-b:a', '320k',
            '-t', f'{duration:.3f}', '-movflags', '+faststart', out]
    return cmd


def spin_clip_command(width, height, fps, out, ffmpeg='ffmpeg'):
    """Encode raw RGB frames from stdin as a lossless clip (the one revolution
    of the record). yuv420p on purpose: the final video is 4:2:0 too, so
    nothing is lost that would have survived, and the overlay stays cheap."""
    return [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}',
            '-framerate', str(fps), '-i', '-',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-qp', '0', '-pix_fmt', 'yuv420p', out]


def wav_duration(path):
    with wave.open(path, 'rb') as w:
        return w.getnframes() / float(w.getframerate())


def _save(surface, path):
    pygame.image.save(surface, path)
    return path


def render_layers(plan, display, tmp, fps, ffmpeg='ffmpeg'):
    """Draw every layer once. Returns what compose_command needs, except the
    audio: backgrounds, spin, arm."""
    lengths = [t['length'] for t in plan.tracks]
    status0 = plan.status(0.001)

    # Backgrounds: the frame with the record and arm left out, one per track.
    display.draw_record = False
    backgrounds = []
    for i, seconds in enumerate(lengths):
        display._render_playing(plan.status(plan.boundaries[i] + 0.001))
        display.renderer.present()
        png = _save(display.renderer.to_surface(), os.path.join(tmp, f'bg{i:03d}.png'))
        backgrounds.append((png, seconds))
    # The last track's background runs on past the tagged length, so a WAV
    # a hair longer than the tags say never runs out of picture.
    backgrounds[-1] = (backgrounds[-1][0], backgrounds[-1][1] + 5.0)
    full_rect = display._record_rect
    # The crop must lie inside the frame (a very small frame cannot hold the
    # record's minimum size) and be even-sized for the yuv420p clip.
    rect = full_rect.clip(pygame.Rect(0, 0, display.width, display.height))
    rect.width -= rect.width % 2
    rect.height -= rect.height % 2

    # The spin: the kiosk renderer draws the record (body, grooves, shine)
    # at every angle of one revolution; the square under the record is
    # cropped out of each frame and piped into a lossless clip that loops.
    # The square is plain panel colour, so the clip needs no alpha.
    display.draw_record = True
    display.draw_arm = False
    frames = 15 * fps                            # 360 deg / 24 deg per s
    clip = os.path.join(tmp, 'spin.mp4')
    proc = subprocess.Popen(spin_clip_command(rect.width, rect.height, fps, clip, ffmpeg),
                            stdin=subprocess.PIPE)
    try:
        for k in range(frames):
            display._record_angle = (k * 360.0 / frames) % 360.0
            display._render_playing(status0)
            display.renderer.present()
            square = display.renderer.to_surface().subsurface(rect)
            proc.stdin.write(pygame.image.tobytes(square, 'RGB'))
    finally:
        proc.stdin.close()
        if proc.wait():
            raise RuntimeError('ffmpeg could not encode the spin clip')
    display.draw_arm = True
    spin = (clip, rect.x, rect.y)

    # The tonearm: one image per pixel of needle travel, fed at the rate the
    # needle moves, so the step matches the kiosk's own integer positions.
    radius = full_rect.width // 2
    rec_cx, rec_cy = full_rect.centerx, full_rect.centery
    steps = max(2, int((OUTER_GROOVE - INNER_GROOVE) * radius) + 1)
    points = [tonearm_points(rec_cx, rec_cy, radius, k / (steps - 1)) for k in range(steps)]
    xs = [p[0] for pv, nd in points for p in (pv, nd)]
    ys = [p[1] for pv, nd in points for p in (pv, nd)]
    margin = 6
    ax, ay = min(xs) - margin, min(ys) - margin
    aw, ah = max(xs) - ax + margin, max(ys) - ay + margin + 1
    for k, (pivot, needle) in enumerate(points):
        layer = pygame.Surface((aw, ah), pygame.SRCALPHA)
        px, py = pivot[0] - ax, pivot[1] - ay
        nx, ny = needle[0] - ax, needle[1] - ay
        pygame.draw.line(layer, TONEARM_COLOR, (px, py), (nx, ny))
        pygame.draw.line(layer, TONEARM_COLOR, (px, py + 1), (nx, ny + 1))
        pygame.draw.circle(layer, NEEDLE_COLOR, (nx, ny), 3)
        _save(layer, os.path.join(tmp, f'arm{k:04d}.png'))
    arm = (os.path.join(tmp, 'arm%04d.png'), (steps - 1) / max(plan.duration, 0.001), ax, ay)
    return backgrounds, spin, arm


def _parse_progress(line):
    """Seconds encoded so far from an ffmpeg -progress line, or None."""
    if line.startswith('out_time_us='):
        try:
            return int(line.split('=', 1)[1]) / 1e6
        except ValueError:
            return None
    return None


def render(plan, out, width=1920, height=1080, fps=30, settings=None, codec='hevc',
           seconds=None, ffmpeg='ffmpeg', log=print):
    """Render ``plan`` to ``out`` (and ``out`` + '.txt'). ``seconds`` caps the
    length, for previews. Returns the number of frames in the video."""
    if width % 2 or height % 2:
        raise ValueError('width and height must be even (yuv420p)')
    settings = settings or VinylSettings(label='art', label_text='none')
    encoder = pick_encoder(codec, ffmpeg, (width, height))
    paths = [t['path'] for t in plan.tracks]
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix='lp-video-') as tmp:
        wav = os.path.join(tmp, 'album.wav')
        log(f'  decoding {len(paths)} tracks to one gapless stream...')
        subprocess.run(audio_command(paths, wav, ffmpeg), check=True)
        duration = wav_duration(wav)
        if seconds is not None:
            duration = min(duration, float(seconds))
        metadata = os.path.join(tmp, 'chapters.txt')
        with open(metadata, 'w') as f:
            f.write(plan.ffmetadata())

        pygame.init()
        display = headless_display(width, height, settings, plan.cover, plan.album_dir,
                                   title='lp-video')
        log('  drawing the layers...')
        backgrounds, spin, arm = render_layers(plan, display, tmp, fps, ffmpeg)
        total_frames = int(math.ceil(duration * fps))
        log(f'  {plan.title()}: {_mmss(duration)}, {total_frames} frames at '
            f'{width}x{height}@{fps} ({encoder[0]})')

        cmd = compose_command(width, height, fps, backgrounds, spin, arm, wav, metadata,
                              out, encoder, duration, ffmpeg)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        encode_started = time.monotonic()
        last_report = -10.0
        for line in proc.stdout:
            t = _parse_progress(line.strip())
            if t is None or t - last_report < 10.0:
                continue
            last_report = t
            elapsed = time.monotonic() - encode_started
            speed = t / elapsed if elapsed > 0 else 0.0
            eta = (duration - t) / speed if speed > 0 else 0.0
            log(f'  {_mmss(t)} / {_mmss(duration)}  {speed:.1f}x realtime, '
                f'about {_mmss(eta)} to go')
        stderr = proc.stderr.read()
        code = proc.wait()
        if code:
            raise RuntimeError(f'ffmpeg exited {code}: {stderr.strip()[-2000:]}')

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
    ap.add_argument('--codec', choices=sorted(ENCODERS), default='hevc',
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
