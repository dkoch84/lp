import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel


class PlayRequest(BaseModel):
    path: str


class VinylStyleRequest(BaseModel):
    style: str


class LabelRequest(BaseModel):
    label: str


class LabelTextRequest(BaseModel):
    mode: str = None
    font: str = None
    artist_color: str = None
    album_color: str = None
    decor1: str = None
    decor1_color: str = None
    decor2: str = None
    decor2_color: str = None


class BrightnessRequest(BaseModel):
    brightness: int


class LastfmAuthRequest(BaseModel):
    username: str
    password: str


class LastfmToggleRequest(BaseModel):
    enabled: bool


class FavoriteRequest(BaseModel):
    favorite: bool


class GridRequest(BaseModel):
    folders: list[str]


LABEL_TEXT_MODES = ['none', 'curved', 'straight', 'blocky']
LABEL_TEXT_FONTS = ['georgia', 'dejavuserif', 'dejavusans', 'dejavusansmono',
                    'oswald', 'bebasneue', 'notoserif', 'notosans', 'ubuntu', 'cantarell']


def create_app(player, library, static_dir, scrobbler=None, display=None, state=None):
    app = FastAPI(title="lp")

    @app.post("/api/share")
    def share():
        """Capture the current display as a PNG and return it for download."""
        if display is None:
            raise HTTPException(503, "display not available")
        data = display.request_screenshot()
        if not data:
            raise HTTPException(503, "screenshot capture failed or timed out")
        import time as _t
        filename = f"lp-{int(_t.time())}.png"
        return Response(
            content=data,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # --- Library browsing ---

    def _artist_covers(a):
        """Folder names for the artist's collage: a user-chosen selection if
        set (filtered to covers that still exist), else the first 4 with art."""
        default = [al.folder_name for al in a.albums if al.cover_path][:4]
        if state:
            saved = state.get_grid_covers(a.name)
            if saved:
                have = {al.folder_name for al in a.albums if al.cover_path}
                sel = [f for f in saved if f in have][:4]
                if sel:
                    return sel
        return default

    @app.get("/api/artists")
    def list_artists():
        return [
            {
                "name": a.name,
                "album_count": len(a.albums),
                "covers": _artist_covers(a),
                "favorite": state.is_favorite(a.name) if state else False,
                "last_played": state.get_last_played(a.name) if state else None,
            }
            for a in library.get_artists()
        ]

    @app.post("/api/artists/{name}/grid")
    def set_grid_covers(name: str, req: GridRequest):
        if not state:
            raise HTTPException(503, "state not available")
        artist = library.get_artist(name)
        if not artist:
            raise HTTPException(404, "Artist not found")
        have = {al.folder_name for al in artist.albums if al.cover_path}
        sel = [f for f in req.folders if f in have][:4]  # validate + cap at 4
        state.set_grid_covers(name, sel)
        return {"name": name, "covers": sel}

    @app.post("/api/artists/{name}/favorite")
    def set_favorite(name: str, req: FavoriteRequest):
        if not state:
            raise HTTPException(503, "state not available")
        if not library.get_artist(name):
            raise HTTPException(404, "Artist not found")
        state.set_favorite(name, req.favorite)
        return {"name": name, "favorite": req.favorite}

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
    def album_cover(artist: str, folder: str, size: str = None):
        artist_obj = library.get_artist(artist)
        if not artist_obj:
            raise HTTPException(404, "Artist not found")
        # Covers rarely change; let the browser hold them for a week so repeat
        # navigation doesn't refetch (or even revalidate) every tile.
        cache = {"Cache-Control": "public, max-age=604800"}
        for album in artist_obj.albums:
            if album.folder_name == folder:
                if not (album.cover_path and os.path.isfile(album.cover_path)):
                    raise HTTPException(404, "No cover art")
                # Grid tiles request a small thumbnail instead of the full,
                # often multi-megabyte, original.
                if size == "thumb":
                    from lp.thumbs import get_thumbnail
                    data = get_thumbnail(album.cover_path)
                    if data:
                        return Response(content=data, media_type="image/jpeg",
                                        headers=cache)
                return FileResponse(album.cover_path, headers=cache)
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
        if state:
            state.mark_played(album.artist)
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
                                MANDELBROT_ZOOMS, NEBULA_VARIANTS,
                                MUNAFO_VARIANTS, VINYL_COLORS)
        mandelbrot_combo = ['mandelbrot-' + v[4] + '-' + v[5] for v in MANDELBROT_VARIANTS]
        mandelbrot_colors = ['mandelbrot-' + c for c in MANDELBROT_COLORS]
        mandelbrot_zooms = ['mandelbrot-' + z[4] for z in MANDELBROT_ZOOMS]
        nebula_names = ['nebula-' + v[2] for v in NEBULA_VARIANTS]
        munafo_names = ['munafo-' + v[0] for v in MUNAFO_VARIANTS]
        color_names = ['color-' + c for c in VINYL_COLORS]
        # Pattern picture-disc: same selectors as the fractal styles, just
        # with a 'pattern-' prefix and no label drawn.
        pattern_basic = ['pattern', 'pattern-mandelbrot', 'pattern-nebula',
                         'pattern-munafo']
        pattern_combo = (['pattern-' + s for s in mandelbrot_combo]
                         + ['pattern-' + s for s in nebula_names]
                         + ['pattern-' + s for s in munafo_names])
        valid = (['random', 'black', 'clear', 'picture',
                  'mandelbrot', 'nebula', 'munafo', 'color']
                 + color_names + mandelbrot_combo + mandelbrot_colors
                 + mandelbrot_zooms + nebula_names + munafo_names
                 + pattern_basic + pattern_combo)
        if req.style not in valid:
            raise HTTPException(400, f"Invalid style. Choose from: {', '.join(valid)}")
        player.vinyl_style = req.style
        return {"style": player.vinyl_style}

    @app.get("/api/settings/vinyl/options")
    def get_vinyl_options():
        from lp.display import (MANDELBROT_VARIANTS, MANDELBROT_COLORS,
                                MANDELBROT_ZOOMS, NEBULA_VARIANTS,
                                MUNAFO_VARIANTS, VINYL_COLORS)
        mandelbrot_combo = [{'id': 'mandelbrot-' + v[4] + '-' + v[5],
                             'label': v[4].replace('-', ' ').title() + ' ' + v[5].title(),
                             'category': 'mandelbrot'}
                            for v in MANDELBROT_VARIANTS]
        nebula_items = [{'id': 'nebula-' + v[2],
                         'label': v[2].replace('-', ' ').title(),
                         'category': 'nebula'}
                        for v in NEBULA_VARIANTS]
        munafo_items = [{'id': 'munafo-' + v[0],
                         'label': v[2] if len(v) > 2 else v[0],
                         'category': 'munafo'}
                        for v in MUNAFO_VARIANTS]
        color_items = [{'id': 'color-' + name,
                        'label': name.replace('-', ' ').title(),
                        'category': 'color'}
                       for name in VINYL_COLORS]
        pattern_basic = [
            {'id': 'pattern', 'label': 'Random Pattern Disc', 'category': 'pattern'},
            {'id': 'pattern-mandelbrot', 'label': 'Random Mandelbrot Pattern', 'category': 'pattern'},
            {'id': 'pattern-nebula', 'label': 'Random Nebula Pattern', 'category': 'pattern'},
            {'id': 'pattern-munafo', 'label': 'Random Munafo Pattern', 'category': 'pattern'},
        ]
        pattern_mandelbrot = [{'id': 'pattern-mandelbrot-' + v[4] + '-' + v[5],
                               'label': v[4].replace('-', ' ').title() + ' ' + v[5].title(),
                               'category': 'pattern'}
                              for v in MANDELBROT_VARIANTS]
        pattern_nebula = [{'id': 'pattern-nebula-' + v[2],
                           'label': v[2].replace('-', ' ').title(),
                           'category': 'pattern'}
                          for v in NEBULA_VARIANTS]
        pattern_munafo = [{'id': 'pattern-munafo-' + v[0],
                           'label': (v[2] if len(v) > 2 else v[0]),
                           'category': 'pattern'}
                          for v in MUNAFO_VARIANTS]
        basic = [
            {'id': 'random', 'label': 'Random', 'category': 'basic'},
            {'id': 'black', 'label': 'Black', 'category': 'basic'},
            {'id': 'clear', 'label': 'Clear', 'category': 'basic'},
            {'id': 'picture', 'label': 'Album Art', 'category': 'basic'},
            {'id': 'color', 'label': 'Random Color', 'category': 'basic'},
            {'id': 'mandelbrot', 'label': 'Random Mandelbrot', 'category': 'basic'},
            {'id': 'nebula', 'label': 'Random Nebula', 'category': 'basic'},
            {'id': 'munafo', 'label': 'Random Munafo Deep-Zoom', 'category': 'basic'},
        ]
        return {'options': (basic + color_items
                            + mandelbrot_combo + nebula_items + munafo_items
                            + pattern_basic + pattern_mandelbrot
                            + pattern_nebula + pattern_munafo)}

    @app.get("/api/vinyl/preview/{style:path}")
    def vinyl_preview(style: str):
        from lp.display import (CACHE_DIR, NEBULA_CACHE_DIR, JULIA_CACHE_DIR,
                                MUNAFO_CACHE_DIR)
        # Vinyl previews are content-addressable by style id and effectively
        # never change once cached, so let the browser hold onto them for a
        # year. New variants get new ids; cached previews are stable.
        headers = {'Cache-Control': 'public, max-age=31536000, immutable'}

        def _serve(path):
            return FileResponse(path, media_type='image/png', headers=headers)

        # Julia previews come in as "julia-dendrite" etc — strip the prefix.
        if style.startswith('julia-'):
            jpath = os.path.join(JULIA_CACHE_DIR, f'{style[len("julia-"):]}.png')
            if os.path.isfile(jpath):
                return _serve(jpath)
        # Munafo previews come in as "munafo-deep5_v1" etc.
        if style.startswith('munafo-'):
            mpath = os.path.join(MUNAFO_CACHE_DIR, f'{style[len("munafo-"):]}.png')
            if os.path.isfile(mpath):
                return _serve(mpath)
        # Try mandelbrot cache: style is "seahorse-purple" etc
        path = os.path.join(CACHE_DIR, f'{style}.png')
        if os.path.isfile(path):
            return _serve(path)
        # Try nebula cache: style is "lava-lamp" etc
        path = os.path.join(NEBULA_CACHE_DIR, f'{style}.png')
        if os.path.isfile(path):
            return _serve(path)
        # Try munafo cache: style is "deep5_v1" etc (UI strips the prefix)
        path = os.path.join(MUNAFO_CACHE_DIR, f'{style}.png')
        if os.path.isfile(path):
            return _serve(path)
        raise HTTPException(404, "No preview available")

    # --- Label settings ---

    @app.get("/api/settings/label")
    def get_label():
        return {"label": player.vinyl_label}

    @app.post("/api/settings/label")
    def set_label(req: LabelRequest):
        from lp.display import (LABEL_COLORS, VINYL_COLORS, MANDELBROT_VARIANTS,
                                NEBULA_VARIANTS, MUNAFO_VARIANTS)
        valid = (['art']
                 + ['color-' + c for c in VINYL_COLORS]
                 + ['label-' + c for c in LABEL_COLORS]  # legacy, still accepted
                 + ['mandelbrot-' + v[4] + '-' + v[5] for v in MANDELBROT_VARIANTS]
                 + ['nebula-' + v[2] for v in NEBULA_VARIANTS]
                 + ['munafo-' + v[0] for v in MUNAFO_VARIANTS])
        if req.label not in valid:
            raise HTTPException(400, f"Invalid label. Choose from: {', '.join(valid)}")
        player.vinyl_label = req.label
        return {"label": player.vinyl_label}

    @app.get("/api/settings/label/options")
    def get_label_options():
        from lp.display import (LABEL_COLORS, MANDELBROT_VARIANTS,
                                NEBULA_VARIANTS, MUNAFO_VARIANTS)
        options = [{'id': 'art', 'label': 'Album Art', 'category': 'basic'}]
        for name in LABEL_COLORS:
            options.append({'id': 'label-' + name, 'label': name.title(),
                            'category': 'color'})
        for v in MANDELBROT_VARIANTS:
            options.append({'id': 'mandelbrot-' + v[4] + '-' + v[5],
                            'label': v[4].replace('-', ' ').title() + ' ' + v[5].title(),
                            'category': 'mandelbrot'})
        for v in NEBULA_VARIANTS:
            options.append({'id': 'nebula-' + v[2],
                            'label': v[2].replace('-', ' ').title(),
                            'category': 'nebula'})
        for v in MUNAFO_VARIANTS:
            options.append({'id': 'munafo-' + v[0],
                            'label': v[2] if len(v) > 2 else v[0],
                            'category': 'munafo'})
        return {'options': options}

    # --- Label text (mode + font) ---

    def _label_text_state():
        p = player
        return {"mode": p.vinyl_label_text, "font": p.vinyl_label_font,
                "artist_color": p.vinyl_label_artist_color,
                "album_color": p.vinyl_label_album_color,
                "decor1": p.vinyl_label_decor1, "decor1_color": p.vinyl_label_decor1_color,
                "decor2": p.vinyl_label_decor2, "decor2_color": p.vinyl_label_decor2_color}

    def _valid_color(c):
        return c == 'auto' or (isinstance(c, str) and len(c) == 7 and c[0] == '#')

    @app.get("/api/settings/label-text")
    def get_label_text():
        return _label_text_state()

    @app.post("/api/settings/label-text")
    def set_label_text(req: LabelTextRequest):
        from lp.display import DECOR_EMOJI
        decor_vals = ['none', 'random'] + list(DECOR_EMOJI)
        if req.mode is not None:
            if req.mode not in LABEL_TEXT_MODES:
                raise HTTPException(400, f"Invalid mode. Choose from: {', '.join(LABEL_TEXT_MODES)}")
            player.vinyl_label_text = req.mode
        if req.font is not None:
            player.vinyl_label_font = req.font
        for field, val in (('vinyl_label_artist_color', req.artist_color),
                           ('vinyl_label_album_color', req.album_color),
                           ('vinyl_label_decor1_color', req.decor1_color),
                           ('vinyl_label_decor2_color', req.decor2_color)):
            if val is not None:
                if not _valid_color(val):
                    raise HTTPException(400, f"Invalid color: {val}")
                setattr(player, field, val)
        for field, val in (('vinyl_label_decor1', req.decor1),
                           ('vinyl_label_decor2', req.decor2)):
            if val is not None:
                if val not in decor_vals:
                    raise HTTPException(400, f"Invalid decor. Choose from: {', '.join(decor_vals)}")
                setattr(player, field, val)
        return _label_text_state()

    @app.get("/api/settings/label-text/options")
    def get_label_text_options():
        from lp.display import DECOR_EMOJI
        fonts = LABEL_TEXT_FONTS
        try:
            import pygame.font as _pf
            _pf.init()
            avail = [f for f in LABEL_TEXT_FONTS if _pf.match_font(f)]
            if avail:
                fonts = avail
        except Exception:
            pass
        return {"modes": LABEL_TEXT_MODES, "fonts": fonts,
                "decors": ['none', 'random'] + list(DECOR_EMOJI),
                **_label_text_state()}

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
        _prewarm_thumbs()  # warm thumbnails for any newly-found covers
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

    # --- Thumbnail prewarm ---
    # Warm the album-art thumbnail cache in the background so the very first
    # browse is fast, not just repeat visits.
    def _prewarm_thumbs():
        from lp.thumbs import start_prewarm
        start_prewarm(a.cover_path for a in library.albums_by_path.values())

    _prewarm_thumbs()

    # --- Static files ---

    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
