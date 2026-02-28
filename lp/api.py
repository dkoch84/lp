import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel


class PlayRequest(BaseModel):
    path: str


class VinylStyleRequest(BaseModel):
    style: str


class LabelRequest(BaseModel):
    label: str


class BrightnessRequest(BaseModel):
    brightness: int


class LastfmAuthRequest(BaseModel):
    username: str
    password: str


class LastfmToggleRequest(BaseModel):
    enabled: bool


def create_app(player, library, static_dir, scrobbler=None):
    app = FastAPI(title="lp")

    # --- Library browsing ---

    @app.get("/api/artists")
    def list_artists():
        return [
            {
                "name": a.name,
                "album_count": len(a.albums),
                "covers": [
                    album.folder_name
                    for album in a.albums[:4]
                    if album.cover_path
                ],
            }
            for a in library.get_artists()
        ]

    @app.get("/api/artists/{name}/albums")
    def artist_albums(name: str):
        artist = library.get_artist(name)
        if not artist:
            raise HTTPException(404, "Artist not found")
        return [
            {
                "name": a.display_name,
                "folder": a.folder_name,
                "year": a.year,
                "track_count": a.track_count,
                "has_cover": a.cover_path is not None,
            }
            for a in artist.albums
        ]

    @app.get("/api/albums/{artist}/{folder}/cover")
    def album_cover(artist: str, folder: str):
        artist_obj = library.get_artist(artist)
        if not artist_obj:
            raise HTTPException(404, "Artist not found")
        for album in artist_obj.albums:
            if album.folder_name == folder:
                if album.cover_path and os.path.isfile(album.cover_path):
                    return FileResponse(album.cover_path)
                raise HTTPException(404, "No cover art")
        raise HTTPException(404, "Album not found")

    @app.get("/api/albums/{artist}/{folder}/tracks")
    def album_tracks(artist: str, folder: str):
        artist_obj = library.get_artist(artist)
        if not artist_obj:
            raise HTTPException(404, "Artist not found")
        for album in artist_obj.albums:
            if album.folder_name == folder:
                tracks = library.get_album_tracks(album.path)
                return {"tracks": tracks, "path": album.path}
        raise HTTPException(404, "Album not found")

    # --- Playback ---

    @app.post("/api/play")
    def play(req: PlayRequest):
        album = library.get_album_by_path(req.path)
        if not album:
            raise HTTPException(400, "Album path not in library")
        player.play_album(req.path)
        return {"status": "playing", "album": album.display_name}

    @app.post("/api/stop")
    def stop():
        player.stop()
        return {"status": "stopped"}

    @app.get("/api/status")
    def status():
        return player.get_status()

    # --- Settings ---

    @app.get("/api/settings/vinyl")
    def get_vinyl_style():
        return {"style": player.vinyl_style}

    @app.post("/api/settings/vinyl")
    def set_vinyl_style(req: VinylStyleRequest):
        from lp.display import (MANDELBROT_VARIANTS, MANDELBROT_COLORS,
                                MANDELBROT_ZOOMS, NEBULA_VARIANTS, VINYL_COLORS)
        mandelbrot_combo = ['mandelbrot-' + v[4] + '-' + v[5] for v in MANDELBROT_VARIANTS]
        mandelbrot_colors = ['mandelbrot-' + c for c in MANDELBROT_COLORS]
        mandelbrot_zooms = ['mandelbrot-' + z[4] for z in MANDELBROT_ZOOMS]
        nebula_names = ['nebula-' + v[2] for v in NEBULA_VARIANTS]
        color_names = ['color-' + c for c in VINYL_COLORS]
        valid = (['random', 'black', 'clear', 'picture', 'mandelbrot', 'nebula', 'color']
                 + color_names + mandelbrot_combo + mandelbrot_colors + mandelbrot_zooms + nebula_names)
        if req.style not in valid:
            raise HTTPException(400, f"Invalid style. Choose from: {', '.join(valid)}")
        player.vinyl_style = req.style
        return {"style": player.vinyl_style}

    @app.get("/api/settings/vinyl/options")
    def get_vinyl_options():
        from lp.display import (MANDELBROT_VARIANTS, MANDELBROT_COLORS,
                                MANDELBROT_ZOOMS, NEBULA_VARIANTS, VINYL_COLORS)
        mandelbrot_combo = [{'id': 'mandelbrot-' + v[4] + '-' + v[5],
                             'label': v[4].replace('-', ' ').title() + ' ' + v[5].title(),
                             'category': 'mandelbrot'}
                            for v in MANDELBROT_VARIANTS]
        nebula_items = [{'id': 'nebula-' + v[2],
                         'label': v[2].replace('-', ' ').title(),
                         'category': 'nebula'}
                        for v in NEBULA_VARIANTS]
        color_items = [{'id': 'color-' + name,
                        'label': name.replace('-', ' ').title(),
                        'category': 'color'}
                       for name in VINYL_COLORS]
        basic = [
            {'id': 'random', 'label': 'Random', 'category': 'basic'},
            {'id': 'black', 'label': 'Black', 'category': 'basic'},
            {'id': 'clear', 'label': 'Clear', 'category': 'basic'},
            {'id': 'picture', 'label': 'Picture Disc', 'category': 'basic'},
            {'id': 'color', 'label': 'Random Color', 'category': 'basic'},
            {'id': 'mandelbrot', 'label': 'Random Mandelbrot', 'category': 'basic'},
            {'id': 'nebula', 'label': 'Random Nebula', 'category': 'basic'},
        ]
        return {'options': basic + color_items + mandelbrot_combo + nebula_items}

    @app.get("/api/vinyl/preview/{style:path}")
    def vinyl_preview(style: str):
        from lp.display import CACHE_DIR, NEBULA_CACHE_DIR
        # Try mandelbrot cache: style is "seahorse-purple" etc
        path = os.path.join(CACHE_DIR, f'{style}.png')
        if os.path.isfile(path):
            return FileResponse(path, media_type='image/png')
        # Try nebula cache: style is "lava-lamp" etc
        path = os.path.join(NEBULA_CACHE_DIR, f'{style}.png')
        if os.path.isfile(path):
            return FileResponse(path, media_type='image/png')
        raise HTTPException(404, "No preview available")

    # --- Label settings ---

    @app.get("/api/settings/label")
    def get_label():
        return {"label": player.vinyl_label}

    @app.post("/api/settings/label")
    def set_label(req: LabelRequest):
        from lp.display import LABEL_COLORS
        valid = ['art'] + ['label-' + c for c in LABEL_COLORS]
        if req.label not in valid:
            raise HTTPException(400, f"Invalid label. Choose from: {', '.join(valid)}")
        player.vinyl_label = req.label
        return {"label": player.vinyl_label}

    @app.get("/api/settings/label/options")
    def get_label_options():
        from lp.display import LABEL_COLORS
        options = [{'id': 'art', 'label': 'Album Art'}]
        for name in LABEL_COLORS:
            options.append({'id': 'label-' + name, 'label': name.title()})
        return {'options': options}

    # --- Brightness settings ---

    @app.get("/api/settings/brightness")
    def get_brightness():
        return {"brightness": player.vinyl_brightness}

    @app.post("/api/settings/brightness")
    def set_brightness(req: BrightnessRequest):
        if not (0 <= req.brightness <= 100):
            raise HTTPException(400, "Brightness must be 0-100")
        player.vinyl_brightness = req.brightness
        return {"brightness": player.vinyl_brightness}

    # --- Library management ---

    @app.post("/api/library/rescan")
    def rescan():
        library.scan()
        return {"artists": len(library.artists), "albums": len(library.albums_by_path)}

    # --- Last.fm ---

    @app.get("/api/settings/lastfm")
    def get_lastfm():
        if not scrobbler:
            return {"configured": False, "authenticated": False, "enabled": False,
                    "username": None, "pylast_available": False}
        return scrobbler.get_status()

    @app.post("/api/settings/lastfm/auth")
    def lastfm_auth(req: LastfmAuthRequest):
        if not scrobbler:
            raise HTTPException(400, "Scrobbler not initialized")
        ok, err = scrobbler.authenticate(req.username, req.password)
        if not ok:
            raise HTTPException(400, err or "Authentication failed")
        return scrobbler.get_status()

    @app.post("/api/settings/lastfm/logout")
    def lastfm_logout():
        if not scrobbler:
            raise HTTPException(400, "Scrobbler not initialized")
        scrobbler.logout()
        return scrobbler.get_status()

    @app.post("/api/settings/lastfm/toggle")
    def lastfm_toggle(req: LastfmToggleRequest):
        if not scrobbler:
            raise HTTPException(400, "Scrobbler not initialized")
        scrobbler.enabled = req.enabled
        return scrobbler.get_status()

    # --- Static files ---

    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
