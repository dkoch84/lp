import argparse
import os
import threading

import yaml
import uvicorn

from lp.player import PlayerBackend
from lp.library import Library
from lp.api import create_app
from lp.scrobbler import Scrobbler
from lp.state import UserState


def main():
    parser = argparse.ArgumentParser(description='lp — album player')
    parser.add_argument('-c', '--config', default='config.yml', help='Path to config file')
    parser.add_argument('--no-display', action='store_true', help='Run without pygame display')
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    music_path = config.get('music_library_path', '/mnt/share/media/Music')
    api_config = config.get('api', {})
    host = api_config.get('host', '0.0.0.0')
    port = api_config.get('port', 8000)

    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

    url = f"http://localhost:{port}"
    print(f"\n  lp remote: {url}\n")

    player = PlayerBackend()
    library = Library(music_path)
    lastfm_config = config.get('lastfm', {})
    scrobbler = Scrobbler(player, lastfm_config)
    state_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '.lp_state.json'
    )
    state = UserState(state_path)

    if args.no_display:
        app = create_app(player, library, static_dir, scrobbler, state=state)
        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        from lp.display import Display
        display = Display(config, player, port)
        app = create_app(player, library, static_dir, scrobbler, display, state)
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
