"""VinylSettings — the display configuration for the spinning vinyl.

Previously these were loose ``vinyl_*`` attributes on PlayerBackend (which mixed
audio playback with display config). They now live here as a single validated
object that both apps own at the app level and hand to the renderer, the web
API, and (soon) lp-deck's controls.

Style/label *validity* against the full variant catalog is still checked at the
web-API layer for now — those big tables move into lpcore.vinyl with the
renderer in the next step, after which validation consolidates here.
"""
from dataclasses import dataclass, asdict, field, fields

from .catalog import LABEL_TEXT_MODES, LABEL_TEXT_FONTS, DECOR_VALUES, GROOVE_TREATMENTS, VINYL_EFFECTS


def valid_color(c):
    """A label/decor color is 'auto' (= derive from the label accent) or #rrggbb."""
    return c == 'auto' or (isinstance(c, str) and len(c) == 7 and c[0] == '#')


@dataclass
class VinylSettings:
    style: str = 'black'              # product default: black vinyl,
    label: str = 'label-white'        # white label
    brightness: int = 100
    label_text: str = 'curved'        # none | curved | straight | blocky
    label_font: str = 'georgia'
    artist_color: str = 'auto'        # 'auto' | '#rrggbb'
    album_color: str = 'auto'
    decor1: str = 'none'
    decor1_color: str = 'auto'
    decor2: str = 'none'
    decor2_color: str = 'auto'
    effects: list = field(default_factory=list)   # Vinyl Effects ids, see effects.py
    grooves: str = 'auto'             # auto | shine | shadow | smooth
    # The kiosk frame (behind everything, and the idle screen) and the panel
    # beside the art that the record sits on. 'auto' is the built-in near
    # black; a cover with a true-black edge wants '#000000' so the panel does
    # not read as a grey slab next to it.
    frame_color: str = 'auto'
    panel_color: str = 'auto'

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in known})

    def update(self, **changes):
        """Validate and apply one or more changes; None values are skipped.

        Raises ValueError on an invalid value (nothing is applied for that key).
        ``style`` and ``label`` are accepted as-is here — their validity against
        the full variant catalog is enforced by the caller (web API) for now.
        """
        for key, value in changes.items():
            if value is None:
                continue
            self._validate(key, value)
            if key == 'effects':
                value = [e for e in VINYL_EFFECTS if e in value]    # canonical order, no repeats
            setattr(self, key, value)
        return self

    @staticmethod
    def _validate(key, value):
        if key == 'brightness':
            if not (isinstance(value, int) and 0 <= value <= 100):
                raise ValueError(f"brightness must be 0–100, got {value!r}")
        elif key == 'label_text':
            if value not in LABEL_TEXT_MODES:
                raise ValueError(f"label_text must be one of {LABEL_TEXT_MODES}")
        elif key == 'label_font':
            if value not in LABEL_TEXT_FONTS:
                raise ValueError(f"label_font must be one of {LABEL_TEXT_FONTS}")
        elif key in ('artist_color', 'album_color', 'decor1_color', 'decor2_color',
                     'frame_color', 'panel_color'):
            if not valid_color(value):
                raise ValueError(f"{key} must be 'auto' or #rrggbb, got {value!r}")
        elif key in ('decor1', 'decor2'):
            if value not in DECOR_VALUES:
                raise ValueError(f"{key} must be one of {DECOR_VALUES}")
        elif key == 'effects':
            if isinstance(value, str) or not isinstance(value, (list, tuple)):
                raise ValueError(f"effects must be a list of {list(VINYL_EFFECTS)}, got {value!r}")
            unknown = [e for e in value if e not in VINYL_EFFECTS]
            if unknown:
                raise ValueError(f"unknown vinyl effects {unknown}; known: {list(VINYL_EFFECTS)}")
        elif key == 'grooves':
            if value not in GROOVE_TREATMENTS:
                raise ValueError(f"grooves must be one of {list(GROOVE_TREATMENTS)}, got {value!r}")
        # style / label: caller validates against the full catalog (for now).
