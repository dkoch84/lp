"""Tests for the lpcore.lyrics loader/parser (LRC synced + plain unsynced).

The point: pin the parsing rules (multi-timestamp expansion, metadata-tag
skipping, offset shift/clamp, >59 minutes) and the file-resolution order, all
Qt-free and IO-light (sibling files written to a tempdir).

Run standalone (no pytest needed):
    .venv/bin/python tests/test_lyrics.py
or under pytest if installed:
    .venv/bin/python -m pytest tests/
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.lyrics import parse_lrc, load_lyrics, active_index


def test_multi_timestamp_expands_and_sorts():
    lines = parse_lrc("[00:47.00][00:12.00]La la")
    assert lines == [(12.0, "La la"), (47.0, "La la")], lines


def test_sorted_across_lines():
    text = "[00:30.00]second\n[00:10.00]first\n[00:20.00]middle"
    lines = parse_lrc(text)
    assert [t for t, _ in lines] == [10.0, 20.0, 30.0], lines
    assert [s for _, s in lines] == ["first", "middle", "second"], lines


def test_metadata_tags_ignored():
    text = "[ar:Artist]\n[ti:Title]\n[length:03:20]\n[00:05.00]real line"
    lines = parse_lrc(text)
    assert lines == [(5.0, "real line")], lines


def test_no_centiseconds():
    lines = parse_lrc("[01:05]hello")
    assert lines == [(65.0, "hello")], lines


def test_offset_shifts_and_clamps():
    # offset +2000ms => shift 2s earlier (subtract).
    text = "[offset:+2000]\n[00:05.00]a\n[00:01.00]b"
    lines = parse_lrc(text)
    # b at 1.0 - 2.0 = -1.0 clamped to 0.0; a at 5.0 - 2.0 = 3.0
    assert lines == [(0.0, "b"), (3.0, "a")], lines


def test_offset_negative_shifts_later():
    text = "[offset:-1500]\n[00:10.00]x"
    lines = parse_lrc(text)
    assert lines == [(11.5, "x")], lines


def test_minutes_over_59():
    lines = parse_lrc("[61:00.00]long")
    assert lines == [(3660.0, "long")], lines


def test_blank_synced_line_kept():
    lines = parse_lrc("[00:03.00]")
    assert lines == [(3.0, "")], lines


def test_crlf_and_blank_lines():
    text = "[00:01.00]one\r\n\r\n[00:02.00]two\r\n"
    lines = parse_lrc(text)
    assert lines == [(1.0, "one"), (2.0, "two")], lines


def test_active_index_synced():
    lines = [(0.0, "a"), (10.0, "b"), (20.0, "c")]
    assert active_index(lines, -1.0) == -1
    assert active_index(lines, 0.0) == 0
    assert active_index(lines, 5.0) == 0
    assert active_index(lines, 10.0) == 1
    assert active_index(lines, 19.9) == 1
    assert active_index(lines, 100.0) == 2


def test_active_index_unsynced():
    lines = [(None, "a"), (None, "b")]
    assert active_index(lines, 5.0) == -1


def test_load_lyrics_sibling_lrc():
    with tempfile.TemporaryDirectory() as d:
        audio = os.path.join(d, "song.mp3")
        with open(audio, "w") as fh:
            fh.write("not real audio")
        with open(os.path.join(d, "song.lrc"), "w") as fh:
            fh.write("[ar:X]\n[00:01.00]first line\n[00:05.00]second")
        res = load_lyrics(audio)
    assert res["synced"] is True, res
    assert res["lines"][0] == (1.0, "first line"), res
    assert res["source"].endswith("song.lrc"), res


def test_load_lyrics_sibling_txt():
    with tempfile.TemporaryDirectory() as d:
        audio = os.path.join(d, "song.flac")
        with open(audio, "w") as fh:
            fh.write("not real audio")
        with open(os.path.join(d, "song.txt"), "w") as fh:
            fh.write("plain line one\nplain line two")
        res = load_lyrics(audio)
    assert res["synced"] is False, res
    assert res["lines"] == [(None, "plain line one"), (None, "plain line two")], res
    assert res["source"].endswith("song.txt"), res


def test_load_lyrics_none_found():
    with tempfile.TemporaryDirectory() as d:
        audio = os.path.join(d, "song.ogg")
        with open(audio, "w") as fh:
            fh.write("not real audio")
        res = load_lyrics(audio)
    assert res == {"synced": False, "lines": [], "source": ""}, res


if __name__ == '__main__':
    import traceback
    tests = [v for k, v in sorted(globals().items())
             if k.startswith('test_') and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
