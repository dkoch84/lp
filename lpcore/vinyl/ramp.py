"""Brightness ramps for translucent smoke vinyl.

A smoke style is drawn from four colours: the clear body's light and deep
tones, the ink its smoke layers darken towards, and the accent ink of the
darkest threads. It only reads as smoke on a big screen when those step down in
brightness. teal-marble's go 124 / 92 / 32 / 14 in luma. purple-marble, as first
tuned, went 70 / 74 / 75 / 201 and rendered as one flat colour with pale
blotches; nothing flagged it until it was on the kiosk.

``derive_ramp`` builds the three darker colours from the light one at teal's
ratios, in the light colour's hue. ``check_ramp`` and ``check_contrast`` are the
warnings lp-studio shows while a style is tuned.
"""
import colorsys
from dataclasses import dataclass

import numpy as np

LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114])

# Luma of each darker colour as a share of the light colour's, and how its
# saturation scales (darks look richer a little more saturated).
RAMP = {'mid': 0.72, 'ink': 0.25, 'accent_ink': 0.09}
_SAT_SCALE = {'mid': 1.08, 'ink': 1.25, 'accent_ink': 0.6}

# Warning thresholds. teal-marble and every marble built from RAMP pass them;
# the first purple-marble and pink-marble (flat on the big screen) fail.
LIGHT_MIN, LIGHT_MAX = 60.0, 220.0   # light luma with room for a ramp below it
MID_MAX = 0.85                        # mid luma / light luma
INK_MAX = 0.45                        # ink luma / light luma
ACCENT_MAX = 0.75                     # accent luma / ink luma
ACCENT_FLOOR = 20.0                   # accents this dark are dark enough anyway
IQR_MIN = 12.0                        # middle half of the disc's luma; teal spans 25


@dataclass(frozen=True)
class Issue:
    level: str          # 'warn' or 'bad'
    keys: tuple         # which colours it is about: 'light', 'mid', 'ink', 'accent_ink', 'contrast'
    message: str

    def as_dict(self):
        return {'level': self.level, 'keys': list(self.keys), 'message': self.message}


def luma(rgb):
    """Perceived brightness, 0 to 255 (Rec. 601 weights)."""
    return float(LUMA_WEIGHTS @ np.asarray(rgb, dtype=np.float64))


def hue_sat(rgb):
    """(hue in degrees, HSV saturation 0..1) of an 8-bit RGB colour."""
    h, s, _v = colorsys.rgb_to_hsv(*(float(c) / 255.0 for c in rgb))
    return h * 360.0, s


def at_luma(hue_deg, sat, target):
    """The RGB colour of this hue and saturation whose luma is ``target``.

    Luma is linear in HSV value at a fixed hue and saturation, so value is
    solved directly. When even full value is too dark (a bright target in a
    dark hue such as blue), saturation gives way so the brightness is kept.
    """
    target = min(max(float(target), 0.0), 255.0)
    s = min(max(float(sat), 0.0), 1.0)
    while True:
        base = np.array(colorsys.hsv_to_rgb((hue_deg % 360.0) / 360.0, s, 1.0)) * 255.0
        value = target / float(base @ LUMA_WEIGHTS)
        if value <= 1.0 or s <= 0.0:
            return tuple(int(round(c)) for c in np.clip(base * value, 0, 255))
        s = max(0.0, s - 0.02)


def derive_ramp(light):
    """mid, ink and accent_ink for a light body colour, at RAMP's ratios."""
    target = luma(light)
    hue, sat = hue_sat(light)
    return {key: at_luma(hue, min(1.0, sat * _SAT_SCALE[key]), target * share)
            for key, share in RAMP.items()}


def matches_ramp(light, mid, ink, accent_ink, tolerance=4):
    """True when the three darker colours are what derive_ramp gives, within
    ``tolerance`` per channel (so a style saved while linked reopens linked)."""
    want = derive_ramp(light)
    have = {'mid': mid, 'ink': ink, 'accent_ink': accent_ink}
    return all(abs(int(a) - int(b)) <= tolerance
               for key in RAMP for a, b in zip(want[key], have[key]))


def check_ramp(light, mid, ink, accent_ink=None):
    """Warnings for a set of smoke colours that will render flat."""
    issues = []
    lum, mid_l, ink_l = luma(light), luma(mid), luma(ink)
    if lum < LIGHT_MIN:
        issues.append(Issue('bad', ('light',),
                            f'The light body colour is too dark (brightness {lum:.0f}) to leave '
                            f'room for darker smoke. Aim for 100 to 180.'))
    elif lum > LIGHT_MAX:
        issues.append(Issue('warn', ('light',),
                            f'The light body colour is very bright ({lum:.0f}). Smoke over it '
                            f'tends to look washed out; 100 to 180 works best.'))
    if lum > 0 and mid_l > MID_MAX * lum:
        issues.append(Issue('warn', ('mid',),
                            f'The deep body colour is nearly as bright as the light one '
                            f'({mid_l:.0f} against {lum:.0f}), so the body reads flat. '
                            f'Aim for about {RAMP["mid"] * lum:.0f}.'))
    if lum > 0 and ink_l > INK_MAX * lum:
        issues.append(Issue('bad', ('ink',),
                            f'The smoke ink ({ink_l:.0f}) is too close to the body ({lum:.0f}). '
                            f'Smoke only darkens towards it, so it will barely show. '
                            f'Aim for about {RAMP["ink"] * lum:.0f}.'))
    if accent_ink is not None:
        acc_l = luma(accent_ink)
        if acc_l > ACCENT_FLOOR and acc_l > ACCENT_MAX * ink_l:
            issues.append(Issue('bad', ('accent_ink',),
                                f'The accent ink ({acc_l:.0f}) is not darker than the smoke ink '
                                f'({ink_l:.0f}). Accents should be the darkest threads; aim for '
                                f'about {RAMP["accent_ink"] * lum:.0f}.'))
    return issues


def contrast(rgba, width, height, inner=0.0, outer=0.95):
    """Luma percentiles of an RGBA disc render, over opaque pixels between
    ``inner`` and ``outer`` (fractions of the disc radius), so a label in the
    middle or the anti-aliased rim does not count. Returns p2, p25, p75, p98
    and iqr (p75 - p25)."""
    px = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4).astype(np.float64)
    yy, xx = np.mgrid[0:height, 0:width]
    r = np.hypot(xx + 0.5 - width / 2.0, yy + 0.5 - height / 2.0) / (min(width, height) / 2.0)
    mask = (px[..., 3] > 250) & (r >= inner) & (r <= outer)
    if not mask.any():
        return None
    y = px[..., :3][mask] @ LUMA_WEIGHTS
    p2, p25, p75, p98 = (float(v) for v in np.percentile(y, [2, 25, 75, 98]))
    return {'p2': p2, 'p25': p25, 'p75': p75, 'p98': p98, 'iqr': p75 - p25}


def check_contrast(stats):
    """A warning when a render is close to one flat colour."""
    if stats is None or stats['iqr'] >= IQR_MIN:
        return []
    return [Issue('warn', ('contrast',),
                  f'The disc is nearly one flat colour: the middle half of its pixels span '
                  f'{stats["iqr"]:.0f} levels of brightness (teal-marble spans 25). '
                  f'Darken the smoke ink or raise smoke amount.')]
