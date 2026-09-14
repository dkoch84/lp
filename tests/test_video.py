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
from lp.video import AlbumPlan, audio_command, video_command

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


def test_hevc_output_is_what_youtube_and_apple_players_want():
    cmd = video_command(1920, 1080, 30, '/tmp/a.wav', '/tmp/c.txt', 'out.mp4')
    assert cmd[cmd.index('-c:v') + 1] == 'libx265'
    assert cmd[cmd.index('-tag:v') + 1] == 'hvc1'
    assert cmd[cmd.index('-pix_fmt', cmd.index('-c:v')) + 1] == 'yuv420p'
    assert cmd[cmd.index('-c:a') + 1] == 'aac'
    assert cmd[cmd.index('-map_metadata') + 1] == '2', 'chapters come from the third input'
    assert cmd[cmd.index('-s') + 1] == '1920x1080'
    assert cmd[cmd.index('-framerate') + 1] == '30'
    assert '+faststart' in cmd


def test_h264_is_available_for_players_without_hevc():
    cmd = video_command(1280, 720, 60, 'a.wav', 'c.txt', 'o.mp4', codec='h264')
    assert cmd[cmd.index('-c:v') + 1] == 'libx264'
    assert '-tag:v' not in cmd
    with pytest.raises(ValueError):
        video_command(1280, 720, 60, 'a.wav', 'c.txt', 'o.mp4', codec='av1')


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


def _encoder(name):
    out = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True)
    return name in out.stdout


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg not installed')
def test_a_tiny_album_renders_end_to_end(tmp_path):
    codec = 'hevc' if _encoder('libx265') else 'h264' if _encoder('libx264') else None
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
