"""Tests for the Last.fm scrobbler's offline queue.

A scrobble that can't be sent (no network, Last.fm down) is kept on disk and
sent later in batches, instead of being lost.

    .venv/bin/python -m pytest tests/test_scrobble_queue.py
"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpcore.scrobbler import BATCH, MAX_QUEUED_AGE, Scrobbler


class FakePlayer:
    def on(self, event, cb):
        pass


class FakeNetwork:
    def __init__(self, offline=False, batches_before_failing=None):
        self.offline = offline
        self.batches_before_failing = batches_before_failing
        self.single = []
        self.batches = []

    def scrobble(self, **kw):
        if self.offline:
            raise ConnectionError('offline')
        self.single.append(kw)

    def scrobble_many(self, tracks):
        if self.offline or (self.batches_before_failing is not None
                            and len(self.batches) >= self.batches_before_failing):
            raise ConnectionError('still offline')
        self.batches.append(list(tracks))


@pytest.fixture
def make(monkeypatch, tmp_path):
    # never pick up a real session from the checkout
    monkeypatch.setattr(Scrobbler, '_restore_session', lambda self: None)

    def build(network):
        s = Scrobbler(FakePlayer(), {})
        s._queue_path = str(tmp_path / 'queue.json')
        s.network = network
        s.username = 'listener'
        return s
    return build


def _track(title, age=60):
    return {'artist': 'Pallbearer', 'title': title, 'album': 'Heartless',
            'duration': 300, 'start_time': time.time() - age}


def _entry(title, age=60):
    return {'artist': 'Pallbearer', 'title': title, 'album': '', 'duration': 300,
            'timestamp': int(time.time() - age)}


def test_a_scrobble_sent_offline_is_kept(make, tmp_path):
    s = make(FakeNetwork(offline=True))
    s._submit_scrobble(_track('I Saw the End'))
    assert s.pending_scrobbles() == 1
    [kept] = json.loads((tmp_path / 'queue.json').read_text())
    assert kept['title'] == 'I Saw the End' and isinstance(kept['timestamp'], int)


def test_the_next_successful_scrobble_sends_the_queue(make):
    net = FakeNetwork(offline=True)
    s = make(net)
    s._submit_scrobble(_track('A'))
    s._submit_scrobble(_track('B'))
    net.offline = False
    s._submit_scrobble(_track('C'))
    assert [t['title'] for t in net.single] == ['C']
    assert [[t['title'] for t in batch] for batch in net.batches] == [['A', 'B']]
    assert s.pending_scrobbles() == 0


def test_batches_stop_at_a_failure_and_keep_the_rest(make):
    net = FakeNetwork(batches_before_failing=1)
    s = make(net)
    for i in range(BATCH * 2 + 20):
        s._enqueue(_entry(f'T{i}'))
    assert s.flush_queue() == BATCH
    assert s.pending_scrobbles() == BATCH + 20
    assert s._load_queue()[0]['title'] == f'T{BATCH}'


def test_scrobbles_too_old_for_lastfm_are_dropped(make):
    s = make(FakeNetwork())
    s._enqueue(_entry('ancient', age=MAX_QUEUED_AGE + 60))
    s._enqueue(_entry('recent'))
    assert [e['title'] for e in s._load_queue()] == ['recent']


def test_a_corrupt_queue_file_is_treated_as_empty(make, tmp_path):
    s = make(FakeNetwork())
    (tmp_path / 'queue.json').write_text('not json')
    assert s.pending_scrobbles() == 0
    s._enqueue(_entry('A'))
    assert s.pending_scrobbles() == 1


def test_nothing_is_sent_while_signed_out(make):
    net = FakeNetwork()
    s = make(net)
    s._enqueue(_entry('A'))
    s.username = None
    assert s.flush_queue() == 0
    assert s.pending_scrobbles() == 1 and net.batches == []
