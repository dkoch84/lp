import argparse
import os
import sys
import threading
import webbrowser

import yaml
import uvicorn

from lpcore.player import PlayerBackend
from lpcore.library import Library
from lpcore.scrobbler import Scrobbler
from lp.api import create_app
from lp.state import UserState
from lp.launch import resolve_port, lan_ip
from lpcore.vinyl.settings import VinylSettings

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description='lp — album player')
    parser.add_argument('-c', '--config', default='config.yml', help='Path to config file')
    parser.add_argument('--no-display', action='store_true', help='Run without pygame display')
    parser.add_argument('--port', default=None, metavar='PORT',
                        help="Control-server port: a number, or 'random' to pick "
                             "(and remember) a fresh free port. Default: reuse the "
                             "saved port, else random.")
    parser.add_argument('--no-save', action='store_true',
                        help="Don't persist the resolved port to the launch config.")
    parser.add_argument('--open', dest='open', action='store_true', default=None,
                        help='Open the control UI in a browser on launch.')
    parser.add_argument('--no-open', dest='open', action='store_false',
                        help="Don't open a browser on launch.")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    music_path = config.get('music_library_path', '/mnt/share/media/Music')
    api_config = config.get('api', {})
    host = api_config.get('host', '0.0.0.0')

    launch_store = os.path.join(HERE, '.lp_launch.json')
    port, source = resolve_port(args.port, launch_store, host=host, save=not args.no_save)

    static_dir = os.path.join(HERE, 'static')

    url_local = f"http://localhost:{port}"
    ip = lan_ip()
    url_lan = f"http://{ip}:{port}" if ip else None
    print(f"\n  lp control: {url_local}", flush=True)
    if url_lan:
        print(f"  on your network (phone): {url_lan}", flush=True)
    if source == 'saved':
        port_note = 'saved'                       # reused from a previous launch
    else:
        port_note = f"{source}, {'not saved' if args.no_save else 'saved'}"
    print(f"  port {port} ({port_note})\n", flush=True)

    # Open a browser when launched interactively at a desktop (a tty + a display),
    # unless told otherwise. A headless/kiosk launch (systemd, --no-display) gets
    # no local browser — it's controlled from a phone.
    open_browser = args.open
    if open_browser is None:
        open_browser = (not args.no_display) and sys.stdout.isatty()
    if open_browser:
        webbrowser.open(url_local)

    player = PlayerBackend(audio_output=config.get('audio_output', 'alsa'))
    library = Library(music_path)
    lastfm_config = config.get('lastfm', {})
    scrobbler = Scrobbler(player, lastfm_config)
    state_path = os.path.join(HERE, '.lp_state.json')
    state = UserState(state_path)
    # Shared vinyl display config: the web API mutates it, the display reads it.
    settings = VinylSettings()

    if args.no_display:
        app = create_app(player, library, static_dir, scrobbler, state=state,
                         settings=settings)
        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        from lp.display import Display
        display = Display(config, player, port, settings=settings)
        app = create_app(player, library, static_dir, scrobbler, display, state,
                         settings=settings)
        api_thread = threading.Thread(
            target=uvicorn.run,
            args=(app,),
            kwargs={"host": host, "port": port, "log_level": "warning"},
            daemon=True,
        )
        api_thread.start()
        try:
            display.run()
        except KeyboardInterrupt:
            pass
        finally:
            player.shutdown()


if __name__ == '__main__':
    main()
