"""Control-server launch config: a remembered, assignable port.

lp is controlled from a browser, so the only launch knob that matters is which
port the control server listens on. By default we pick a random free port and
remember it, so it's stable across launches without colliding with anything.
It can be assigned explicitly (``--port``) and re-randomized on demand
(``--port random``). The chosen port is persisted to a small JSON store
alongside the config (not config.yml, so hand-written comments there survive).
"""
import json
import os
import socket


def _load(store_path):
    try:
        with open(store_path) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(store_path, data):
    try:
        tmp = store_path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, store_path)
    except Exception as e:
        print(f"Failed to save launch config: {e}")


def find_free_port():
    """An OS-assigned free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def port_is_free(port, host='0.0.0.0'):
    bind_host = '' if host in ('0.0.0.0', '::', '') else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((bind_host, port))
            return True
        except OSError:
            return False


def resolve_port(assigned, store_path, host='0.0.0.0', save=True):
    """Resolve the control-server port.

    Precedence: explicit assigned port > saved launch config > random free port.
    ``assigned`` may be an int/str port, ``'random'`` to force a fresh pick, or
    None/``'auto'`` to use the saved value (falling back to random). The chosen
    port is persisted unless ``save`` is False.

    Returns ``(port, source)`` with source ``'assigned' | 'saved' | 'random'``.
    """
    cfg = _load(store_path)
    norm = assigned.strip().lower() if isinstance(assigned, str) else assigned

    if norm == 'random':
        port, source = find_free_port(), 'random'
    elif norm not in (None, '', 'auto'):
        port = int(assigned)
        if not port_is_free(port, host):
            raise SystemExit(f"Port {port} is already in use — pick another with --port.")
        source = 'assigned'
    elif cfg.get('port') and port_is_free(int(cfg['port']), host):
        port, source = int(cfg['port']), 'saved'
    else:
        # No usable saved port (unset, or taken by another instance) — pick fresh.
        port, source = find_free_port(), 'random'

    if save and cfg.get('port') != port:
        cfg['port'] = port
        _save(store_path, cfg)

    return port, source


def lan_ip():
    """Best-effort primary LAN IP for the phone-control URL (sends no traffic)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
    except Exception:
        return None
