"""Tests for the /api/update endpoints: the web UI's view of lp.update.

A checkout reports managed=false and refuses the actions; a managed install
passes check and install straight through to the UpdateManager, and an
unknown `when` is a 400 rather than a crash.

    .venv/bin/python -m pytest tests/test_api_update.py
"""
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lp.api import create_app


class _Library:
    albums_by_path = {}


class _Player:
    def get_status(self):
        return {"playing": False}


class _Updates:
    def __init__(self, managed):
        self.managed = managed
        self.calls = []

    def status(self):
        return {"managed": self.managed, "current": "karmanjakah", "available": None}

    def check(self):
        self.calls.append("check")
        return {**self.status(), "available": "crucible-and-ruin"}

    def install(self, when):
        if when not in ("now", "idle", "cancel"):
            raise ValueError(when)
        self.calls.append(("install", when))
        return {**self.status(), "pending": when}


def _client(updates):
    return TestClient(create_app(_Player(), _Library(), "/nonexistent", updates=updates))


def test_no_manager_means_unmanaged():
    c = _client(None)
    assert c.get("/api/update").json() == {"managed": False}
    assert c.post("/api/update/check").status_code == 400


def test_a_checkout_is_unmanaged_and_refuses_actions():
    c = _client(_Updates(managed=False))
    assert c.get("/api/update").json()["managed"] is False
    assert c.post("/api/update/check").status_code == 400
    assert c.post("/api/update/install", json={"when": "now"}).status_code == 400


def test_a_managed_install_checks_and_installs():
    u = _Updates(managed=True)
    c = _client(u)
    assert c.post("/api/update/check").json()["available"] == "crucible-and-ruin"
    assert c.post("/api/update/install", json={"when": "idle"}).json()["pending"] == "idle"
    assert c.post("/api/update/install", json={}).json()["pending"] == "idle", "idle is the default"
    assert c.post("/api/update/install", json={"when": "later"}).status_code == 400
    assert u.calls == ["check", ("install", "idle"), ("install", "idle")]
