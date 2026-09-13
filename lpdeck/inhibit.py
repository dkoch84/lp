"""Keep the computer from sleeping while music plays.

Holds a systemd-inhibit lock for as long as a child process runs: starting it
blocks sleep and idle suspend, stopping it lets them happen again. If
systemd-inhibit isn't there, nothing happens.
"""
import logging
import shutil
import subprocess
import threading

log = logging.getLogger("lpdeck.inhibit")


def default_command():
    exe = shutil.which("systemd-inhibit")
    if not exe:
        return None
    return [exe, "--what=sleep:idle", "--who=lp-deck", "--why=Playing music",
            "--mode=block", "sleep", "infinity"]


class SleepInhibitor:
    def __init__(self, command=None):
        self._command = command if command is not None else default_command()
        self._proc = None
        self._lock = threading.Lock()
        self.enabled = True

    @property
    def active(self):
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def set_active(self, on):
        """Hold the lock while `on` and enabled; release it otherwise."""
        on = bool(on) and self.enabled and bool(self._command)
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            if on and not running:
                try:
                    self._proc = subprocess.Popen(self._command, stdin=subprocess.DEVNULL,
                                                  stdout=subprocess.DEVNULL,
                                                  stderr=subprocess.DEVNULL)
                except OSError as e:
                    log.warning("could not keep the computer awake: %s", e)
                    self._proc = None
            elif not on and running:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                self._proc = None

    def shutdown(self):
        self.enabled = False
        self.set_active(False)
