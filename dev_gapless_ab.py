"""Gapless A/B: play the Dove -> 'Eyes seeing eyes' seam on direct ALSA, with and
without VLC audio time-stretch, so the start-of-track-2 clip can be heard.

Run on the odroid (stop lp playback first so ALSA is free — pausing in the web
UI is enough, no need to stop the service):

    ~/lp/venv/bin/python ~/lp/dev_gapless_ab.py
"""
import time

import vlc

BASE = "/mnt/share/media/Music/Karmanjakah/2026 - Diamond morning"
TRACKS = ("01 Dove.flac", "02 Eyes seeing eyes.flac")


def trial(name, *opts):
    print(f"\n=== {name} : {opts or '(none)'} ===", flush=True)
    inst = vlc.Instance("--aout=alsa", *opts)
    lp = inst.media_list_player_new()
    mp = inst.media_player_new()
    lp.set_media_player(mp)
    ml = inst.media_list_new()
    for f in TRACKS:
        ml.add_media(inst.media_new(f"{BASE}/{f}"))
    lp.set_media_list(ml)
    lp.play()
    while mp.get_length() <= 0:
        time.sleep(0.1)
    mp.set_time(mp.get_length() - 6000)   # jump to 6s before Dove ends
    print(">>> SEAM coming — listen to the full first word + intro of track 2", flush=True)
    time.sleep(20)                         # ~6s Dove tail + ~14s into track 2
    lp.stop()
    time.sleep(2)


if __name__ == "__main__":
    trial("1 BASELINE")
    trial("3 NO-TIME-STRETCH", "--no-audio-time-stretch")
    print("\ndone.", flush=True)
