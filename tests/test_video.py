"""Tests for lp.video, the album-to-video renderer.

The plan (which track is on at second t, where the chapters fall, what the
upload description says) is pure and tested exactly. The ffmpeg command lines
are checked for the parts that matter to YouTube and to Apple players (HEVC
tagged hvc1, yuv420p, AAC, chapters mapped in). The one end-to-end test
renders a second of a two-track "album" of generated tones at a tiny size, and
skips when ffmpeg is not installed.

    .venv/bin/python -m pytest tests/test_video.py
"""
import math
import os
import shutil
import struct
import subprocess
import sys
import wave

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lp import video
from lp.video import AlbumPlan, audio_command, compose_command, spin_clip_command

TRACKS = [
    {'title': 'Canyons', 'artist': 'Howling Giant', 'album': 'Crucible & Ruin',
     'date': '2025-05-02', 'length': 401.0, 'path': '/m/1.mp3'},
    {'title': "Hunter's Mark", 'artist': 'Howling Giant', 'album': 'Crucible & Ruin',
     'date': '2025-05-02', 'length': 270.5, 'path': '/m/2.mp3'},
    {'title': 'Archon', 'artist': 'Howling Giant', 'album': 'Crucible & Ruin',
     'date': '2025-05-02', 'length': 362.0, 'path': '/m/3.mp3'},
]


def test_the_plan_knows_which_track_plays_when():
    plan = AlbumPlan(TRACKS)
    assert plan.boundaries == [0.0, 401.0, 671.5]
    assert plan.duration == 1033.5
    assert plan.track_at(0) == 0
    assert plan.track_at(400.99) == 0
    assert plan.track_at(401.0) == 1, 'a boundary belongs to the track it starts'
    assert plan.track_at(700) == 2
    assert plan.track_at(99999) == 2, 'past the end stays on the last track'


def test_the_status_matches_what_the_kiosk_shows():
    s = AlbumPlan(TRACKS).status(500.0)
    assert s['playing'] is True
    assert s['track_number'] == 2
    assert s['total_tracks'] == 3
    assert s['track_title'] == "Hunter's Mark"
    assert s['artist'] == 'Howling Giant'
    assert s['date'] == '2025-05-02'
    assert s['progress'] == {'album_duration': 1033.5, 'elapsed': 500.0,
                             'track_boundaries': [0.0, 401.0, 671.5]}


def test_the_description_is_a_youtube_chapter_list():
    text = AlbumPlan(TRACKS).description()
    lines = text.splitlines()
    assert lines[0] == 'Howling Giant - Crucible & Ruin (2025)'
    assert lines[-3:] == ['00:00 Canyons', "06:41 Hunter's Mark", '11:11 Archon']
    assert text.endswith('\n')


def test_long_albums_get_hour_timestamps():
    long = [dict(t, length=3000.0) for t in TRACKS]
    assert AlbumPlan(long).description().splitlines()[-1] == '1:40:00 Archon'


def test_ffmetadata_has_one_chapter_per_track_in_milliseconds():
    meta = AlbumPlan(TRACKS).ffmetadata()
    assert meta.startswith(';FFMETADATA1\n')
    assert meta.count('[CHAPTER]') == 3
    assert 'START=401000\nEND=671500\ntitle=Hunter\'s Mark' in meta
    assert 'START=671500\nEND=1033500\ntitle=Archon' in meta


def test_an_empty_album_is_refused():
    with pytest.raises(ValueError):
        AlbumPlan([])


def test_audio_is_joined_with_the_concat_filter_not_the_demuxer():
    cmd = audio_command(['/m/1.mp3', '/m/2.flac'], '/tmp/a.wav')
    assert cmd.count('-i') == 2
    assert '[0:a][1:a]concat=n=2:v=0:a=1[a]' in cmd
    assert cmd[-1] == '/tmp/a.wav'
    assert cmd[cmd.index('-ar') + 1] == '48000'


def _compose(encoder=('hevc_nvenc', ['-preset', 'p4', '-tag:v', 'hvc1'])):
    return compose_command(1920, 1080, 30,
                           [('/t/bg000.png', 401.0), ('/t/bg001.png', 270.5), ('/t/bg002.png', 367.0)],
                           ('/t/spin.mp4', 1178, 297),
                           ('/t/arm%04d.png', 0.0663, 1500, 300),
                           '/t/album.wav', '/t/chapters.txt', 'out.mp4', encoder, 1033.5)


def test_the_graph_loops_stills_once_decoded_and_overlays_only_twice():
    cmd = _compose()
    graph = cmd[cmd.index('-filter_complex') + 1]
    assert '-loop' not in cmd, 'image inputs are looped by the filter, not re-decoded per frame'
    assert graph.count('loop=loop=-1:size=1') == 3, 'one per background'
    assert 'trim=duration=401.000' in graph and 'trim=duration=367.000' in graph
    assert 'concat=n=3:v=1:a=0[bg]' in graph
    assert graph.count('overlay=') == 2, 'the spin and the arm'
    assert 'overlay=x=1178:y=297' in graph and 'overlay=x=1500:y=300' in graph
    assert graph.count('format=yuv420p') == 4, 'each background up front, and the output'
    assert 'format=yuva420p[arm]' in graph
    assert cmd[cmd.index('-stream_loop') + 1] == '-1', 'the spin clip loops for the whole album'
    assert cmd[cmd.index('-stream_loop') + 2:cmd.index('-stream_loop') + 4] == ['-i', '/t/spin.mp4']
    assert cmd[cmd.index('-t') + 1] == '1033.500'


def test_hevc_output_is_what_youtube_and_apple_players_want():
    cmd = _compose()
    assert cmd[cmd.index('-c:v') + 1] == 'hevc_nvenc'
    assert cmd[cmd.index('-tag:v') + 1] == 'hvc1'
    assert cmd[cmd.index('-c:a') + 1] == 'aac'
    assert cmd[cmd.index('-map_metadata') + 1] == '6', 'chapters come from the last input'
    assert '+faststart' in cmd
    assert cmd[cmd.index('-progress') + 1] == 'pipe:1', 'progress is read from stdout'


def test_every_encoder_table_entry_tags_hevc_for_apple_players():
    from lp.video import ENCODERS
    for name, args in ENCODERS['hevc']:
        assert args[args.index('-tag:v') + 1] == 'hvc1', name
    for name, args in ENCODERS['h264']:
        assert '-tag:v' not in args, name


def test_b_frames_are_off_wherever_the_encoder_has_the_knob():
    """P-frames sharper than the B-frames between them pulse at 7.5 Hz on a
    slowly turning record; that looked like jitter in the first render."""
    from lp.video import ENCODERS
    for codec, table in ENCODERS.items():
        for name, args in table:
            if 'videotoolbox' in name:
                continue                    # no B-frame option exposed
            joined = ' '.join(args)
            assert '-bf 0' in joined or 'bframes=0' in joined, (codec, name)


def test_pick_encoder_takes_the_first_that_works(monkeypatch):
    from lp import video
    monkeypatch.setattr(video, 'encoder_works', lambda name, ffmpeg='ffmpeg', args=(): name == 'libx265')
    assert video.pick_encoder('hevc')[0] == 'libx265'
    monkeypatch.setattr(video, 'encoder_works', lambda name, ffmpeg='ffmpeg', args=(): False)
    with pytest.raises(RuntimeError, match='no working'):
        video.pick_encoder('hevc')
    with pytest.raises(ValueError):
        video.pick_encoder('av1')


def test_the_spin_clip_is_lossless_and_frame_exact():
    cmd = spin_clip_command(660, 660, 30, '/t/spin.mp4')
    assert cmd[cmd.index('-qp') + 1] == '0'
    assert cmd[cmd.index('-s') + 1] == '660x660'
    assert cmd[cmd.index('-framerate') + 1] == '30'
    assert cmd[cmd.index('-i') + 1] == '-'


def test_odd_sizes_are_refused_before_rendering(tmp_path):
    with pytest.raises(ValueError, match='even'):
        video.render(AlbumPlan(TRACKS), str(tmp_path / 'o.mp4'), width=321, height=180)


def _tone(path, seconds, hz):
    rate = 8000
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * seconds)
        w.writeframes(b''.join(struct.pack('<h', int(12000 * math.sin(2 * math.pi * hz * i / rate)))
                               for i in range(n)))


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg not installed')
def test_a_tiny_album_renders_end_to_end(tmp_path):
    from lp.video import encoder_works
    codec = 'hevc' if encoder_works('libx265') else 'h264' if encoder_works('libx264') else None
    if codec is None:
        pytest.skip('ffmpeg has neither libx265 nor libx264')
    a, b = str(tmp_path / 'a.wav'), str(tmp_path / 'b.wav')
    _tone(a, 0.6, 440)
    _tone(b, 0.6, 660)
    tracks = [
        {'title': 'One', 'artist': 'Band', 'album': 'Tiny', 'date': '2026', 'length': 0.6, 'path': a},
        {'title': 'Two', 'artist': 'Band', 'album': 'Tiny', 'date': '2026', 'length': 0.6, 'path': b},
    ]
    out = str(tmp_path / 'tiny.mp4')
    frames = video.render(AlbumPlan(tracks, album_dir=str(tmp_path)), out,
                          width=160, height=90, fps=10, codec=codec, log=lambda *_: None)

    assert frames == 12
    assert os.path.getsize(out) > 0
    assert (tmp_path / 'tiny.mp4.txt').read_text().splitlines()[-2:] == ['00:00 One', '00:00 Two']
    probe = subprocess.run(['ffprobe', '-hide_banner', out], capture_output=True, text=True).stderr
    assert '160x90' in probe
    assert 'Chapter #0:1' in probe
    assert ('hevc' if codec == 'hevc' else 'h264') in probe
    assert 'Duration: 00:00:01.2' in probe
