"""VinylSettings — the display configuration for the spinning vinyl.

Previously these were loose ``vinyl_*`` attributes on PlayerBackend (which mixed
audio playback with display config). They now live here as a single validated
object that both apps own at the app level and hand to the renderer, the web
API, and (soon) lp-deck's controls.

Style/label *validity* against the full variant catalog is still checked at the
web-API layer for now — those big tables move into lpcore.vinyl with the
renderer in the next step, after which validation consolidates here.
"""
from dataclasses import dataclass, asdict, fields

from .catalog import LABEL_TEXT_MODES, LABEL_TEXT_FONTS, DECOR_VALUES


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
        elif key in ('artist_color', 'album_color', 'decor1_color', 'decor2_color'):
            if not valid_color(value):
                raise ValueError(f"{key} must be 'auto' or #rrggbb, got {value!r}")
        elif key in ('decor1', 'decor2'):
            if value not in DECOR_VALUES:
                raise ValueError(f"{key} must be one of {DECOR_VALUES}")
        # style / label: caller validates against the full catalog (for now).
