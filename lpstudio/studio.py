"""StudioController — live vinyl-style authoring for lp-studio.

Authors a *catalog style* across families by driving lpcore's exact production
renderer:

  * body   — ``VinylRenderer.build_record`` with the style forced onto the
             renderer's style cache (so any family renders the real way),
  * grooves: drawn by the same renderer code lp and lp-deck use, so the
    preview matches what ships,
  * shine: ``build_shine_overlay`` exactly as lp and lp-deck draw it (the
    shine is the same for every style, so it isn't a studio control).

Families:
  * mandelbrot — zoom location + sinusoidal RGB palette (live scheme injected
                 into ``MANDELBROT_COLORS``),
  * color      — solid vinyl (live colour injected into ``VINYL_COLORS``),
  * nebula     — two-colour swirl via the parameterized ``_nebula_palette``
                 factory; the palette closure rides *inside* the variant tuple,
                 so no catalog injection is needed,
  * clouds     — soft painterly clouds via ``_clouds_palette`` (a nebula
                 sub-type that routes to the clouds renderer),
  * smoke      — translucent vinyl with overlapping smoke layers, each rotated
                 and stretched its own way (the ``'layers'`` nebula route),
  * black / clear — built-in bodies.

Nebula exposes a simplified control set (two colours + mode dropdowns) with an
Advanced toggle that reveals the full per-channel amplitude + modulator matrix.
Smoke uses the same toggle to reveal per-layer trims (opacity, amount, stretch,
direction, softness) for every layer.
"""
import json
import os
import random
import sys
import time

from PySide6.QtCore import Property, QObject, QProcess, Signal, Slot

from lpcore.paths import repo_dir
from lpcore.vinyl import catalog, fractals, ramp, styles
from lpcore.vinyl.catalog import MANDELBROT_VARIANTS, MANDELBROT_ZOOMS
from lpcore.vinyl.fractals import (NEBULA_MODS, SMOKE_LAYER_PARAMS, SMOKE_MAX_LAYERS,
                                   _clouds_palette, _nebula_palette)
from lpcore.vinyl.render import VinylRenderer
from lpcore.vinyl.settings import VinylSettings

_LIVE_KEY = "__studio_live__"
_ALBUM = "__studio__"

# Preview against a synthetic 7-track album so the groove band shows realistic
# track-boundary gaps. Track lengths vary (like a real LP) and are fixed/
# deterministic so the gap rings stay put across re-renders. boundaries = track
# start times (cumulative); the renderer carves a gap at each boundary[1:], so
# 7 tracks → 6 unevenly-spaced gaps.
_STUDIO_TRACK_LENS = (252, 190, 318, 165, 287, 214, 339)   # seconds
_STUDIO_ALBUM_DUR = float(sum(_STUDIO_TRACK_LENS))
_STUDIO_BOUNDARIES = [sum(_STUDIO_TRACK_LENS[:i])
                      for i in range(len(_STUDIO_TRACK_LENS))]

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

FAMILIES = ["mandelbrot", "color", "nebula", "clouds", "smoke", "black", "clear"]

# Nebula choice enums (stored as integer indices in the param dict).
BRIGHT_MODES = ["std", "galaxy", "pastel"]
BRIGHT_LABELS = ["Standard", "Galaxy (br²)", "Pastel"]
SPARKLE_MODES = ["none", "stars", "pop"]
SPARKLE_LABELS = ["None", "Stars", "Pop"]
MOD_LABELS = list(NEBULA_MODS)        # t1 / t2 / t3 / hs / inv_t3 / sin

# Default per-channel modulation depth for nebula simple mode (scaled by contrast).
DEFAULT_AMP1 = (200.0, 60.0, 135.0)
DEFAULT_AMP2 = (55.0, 140.0, 40.0)

DEFAULTS = {
    # mandelbrot
    "cx": -0.7463, "cy": 0.1102, "zoom": 80.0, "max_iter": 200,
    "int_r": 15, "int_g": 5, "int_b": 30,
    "r_base": 40, "r_amp": 180, "r_freq": 12.0, "r_phase": 0.0,
    "g_base": 20, "g_amp": 80, "g_freq": 8.0, "g_phase": 2.0,
    "b_base": 80, "b_amp": 175, "b_freq": 10.0, "b_phase": 4.0,
    # color
    "col_r": 130, "col_g": 35, "col_b": 35,
    # nebula — simple
    "neb_c1_r": 40, "neb_c1_g": 10, "neb_c1_b": 120,
    "neb_c2_r": 200, "neb_c2_g": 80, "neb_c2_b": 5,
    "neb_contrast": 1.0, "neb_sat": 1.5,
    "neb_bright": 0, "neb_sparkle": 0, "neb_seed": 42,
    # nebula — advanced
    "amp1_r": 200, "amp1_g": 60, "amp1_b": 135,
    "amp2_r": 55, "amp2_g": 140, "amp2_b": 40,
    "mod1_r": 0, "mod1_g": 3, "mod1_b": 5,        # t1, hs, sin
    "mod2_r": 2, "mod2_g": 0, "mod2_b": 4,        # t3, t1, inv_t3
    "neb_sin_freq": 8.0, "neb_warp": 6, "neb_arm": 7,
    # clouds
    "cld_cloud_r": 253, "cld_cloud_g": 226, "cld_cloud_b": 233,
    "cld_sky_r": 156, "cld_sky_g": 210, "cld_sky_b": 238,
    "cld_sat": 1.25, "cld_seed": 28,
    # smoke (defaults are the renderer's own, so a fresh smoke style starts as teal-marble)
    "smk_seed": 101, "smk_layers": SMOKE_LAYER_PARAMS["layers"],
    "smk_amount": SMOKE_LAYER_PARAMS["amount"], "smk_opacity": SMOKE_LAYER_PARAMS["opacity"],
    "smk_gamma": SMOKE_LAYER_PARAMS["gamma"], "smk_soft": SMOKE_LAYER_PARAMS["soft"],
    "smk_stretch_lo": SMOKE_LAYER_PARAMS["stretch"][0], "smk_stretch_hi": SMOKE_LAYER_PARAMS["stretch"][1],
    "smk_warp": SMOKE_LAYER_PARAMS["warp_oct"], "smk_arm": SMOKE_LAYER_PARAMS["arm_oct"],
    "smk_deep_soft": SMOKE_LAYER_PARAMS["deep_soft"], "smk_deep_op": SMOKE_LAYER_PARAMS["deep_opacity"],
    "smk_veil_soft": SMOKE_LAYER_PARAMS["veil_soft"],
    "smk_light_r": SMOKE_LAYER_PARAMS["light"][0], "smk_light_g": SMOKE_LAYER_PARAMS["light"][1],
    "smk_light_b": SMOKE_LAYER_PARAMS["light"][2],
    "smk_mid_r": SMOKE_LAYER_PARAMS["mid"][0], "smk_mid_g": SMOKE_LAYER_PARAMS["mid"][1],
    "smk_mid_b": SMOKE_LAYER_PARAMS["mid"][2],
    "smk_ink_r": SMOKE_LAYER_PARAMS["ink"][0], "smk_ink_g": SMOKE_LAYER_PARAMS["ink"][1],
    "smk_ink_b": SMOKE_LAYER_PARAMS["ink"][2],
    "smk_op_var": SMOKE_LAYER_PARAMS["opacity_variation"], "smk_spread": SMOKE_LAYER_PARAMS["spread"],
    "smk_rotate": SMOKE_LAYER_PARAMS["rotate"],
    "smk_shadow": SMOKE_LAYER_PARAMS["shadow"], "smk_shadow_soft": SMOKE_LAYER_PARAMS["shadow_soft"],
    "smk_acc_count": SMOKE_LAYER_PARAMS["accents"], "smk_acc_seed": SMOKE_LAYER_PARAMS["accent_seed"],
    "smk_acc_amount": SMOKE_LAYER_PARAMS["accent_amount"], "smk_acc_opacity": SMOKE_LAYER_PARAMS["accent_opacity"],
    "smk_acc_gamma": SMOKE_LAYER_PARAMS["accent_gamma"], "smk_acc_soft": SMOKE_LAYER_PARAMS["accent_soft"],
    "smk_acc_stretch_lo": SMOKE_LAYER_PARAMS["accent_stretch"][0],
    "smk_acc_stretch_hi": SMOKE_LAYER_PARAMS["accent_stretch"][1],
    "smk_acc_follow": SMOKE_LAYER_PARAMS["accent_follow"],
    "smk_acc_ink_r": SMOKE_LAYER_PARAMS["accent_ink"][0], "smk_acc_ink_g": SMOKE_LAYER_PARAMS["accent_ink"][1],
    "smk_acc_ink_b": SMOKE_LAYER_PARAMS["accent_ink"][2],
}

# Per-layer smoke trims: smk_l<N>_<trim>, N counted from 1 as shown in the panel.
_LAYER_TRIMS = (("opacity", "layer_opacity"), ("amount", "layer_amount"),
                ("stretch", "layer_stretch"), ("angle", "layer_angle"), ("soft", "layer_soft"))
for _n in range(1, SMOKE_MAX_LAYERS + 1):
    for _short, _long in _LAYER_TRIMS:
        DEFAULTS[f"smk_l{_n}_{_short}"] = SMOKE_LAYER_PARAMS[_long][_n - 1]

for _e in catalog.VINYL_EFFECTS:
    DEFAULTS["fx_" + _e.replace("-", "_")] = 0
DEFAULTS["fx_grooves"] = 0      # index into catalog.GROOVE_TREATMENTS; 0 is auto

_INTEGER_KEYS = {
    "max_iter", "int_r", "int_g", "int_b",
    "r_base", "r_amp", "g_base", "g_amp", "b_base", "b_amp",
    "col_r", "col_g", "col_b",
    "neb_c1_r", "neb_c1_g", "neb_c1_b", "neb_c2_r", "neb_c2_g", "neb_c2_b",
    "neb_bright", "neb_sparkle", "neb_seed",
    "amp1_r", "amp1_g", "amp1_b", "amp2_r", "amp2_g", "amp2_b",
    "mod1_r", "mod1_g", "mod1_b", "mod2_r", "mod2_g", "mod2_b",
    "neb_warp", "neb_arm",
    "cld_cloud_r", "cld_cloud_g", "cld_cloud_b",
    "cld_sky_r", "cld_sky_g", "cld_sky_b", "cld_seed",
    "smk_seed", "smk_layers", "smk_soft", "smk_warp", "smk_arm", "smk_deep_soft", "smk_veil_soft",
    "smk_light_r", "smk_light_g", "smk_light_b", "smk_mid_r", "smk_mid_g", "smk_mid_b",
    "smk_ink_r", "smk_ink_g", "smk_ink_b",
    "smk_acc_count", "smk_acc_seed", "smk_acc_soft", "smk_acc_ink_r", "smk_acc_ink_g", "smk_acc_ink_b",
    "smk_shadow_soft", "fx_grooves",
    *(f"smk_l{n}_soft" for n in range(1, SMOKE_MAX_LAYERS + 1)),
}


# ---------------------------------------------------------------- control specs

def _rgb(prefix, names=("R", "G", "B")):
    return [{"key": f"{prefix}_{c}", "label": label, "kind": "slider",
             "min": 0, "max": 255, "integer": True}
            for c, label in zip("rgb", names)]


def _mandel_groups():
    groups = [
        {"group": "Location", "controls": [
            {"key": "cx", "label": "Center X", "kind": "field"},
            {"key": "cy", "label": "Center Y", "kind": "field"},
            {"key": "zoom", "label": "Zoom", "kind": "field"},
            {"key": "max_iter", "label": "Max iterations", "kind": "field", "integer": True},
        ]},
        {"group": "Interior", "controls": _rgb("int")},
    ]
    for ch, label in (("r", "Red"), ("g", "Green"), ("b", "Blue")):
        groups.append({"group": f"{label} channel", "controls": [
            {"key": f"{ch}_base", "label": "Base", "kind": "slider", "min": 0, "max": 255, "integer": True},
            {"key": f"{ch}_amp", "label": "Amplitude", "kind": "slider", "min": 0, "max": 255, "integer": True},
            {"key": f"{ch}_freq", "label": "Frequency", "kind": "slider", "min": 0.0, "max": 24.0, "step": 0.1},
            {"key": f"{ch}_phase", "label": "Phase", "kind": "slider", "min": 0.0, "max": 6.2832, "step": 0.02},
        ]})
    return groups


def _nebula_groups(advanced):
    core = []
    if not advanced:
        core.append({"key": "neb_contrast", "label": "Contrast", "kind": "slider",
                     "min": 0.0, "max": 1.6, "step": 0.02})
    core += [
        {"key": "neb_sat", "label": "Saturation", "kind": "slider", "min": 0.0, "max": 2.0, "step": 0.05},
        {"key": "neb_bright", "label": "Brightness", "kind": "choice", "options": BRIGHT_LABELS},
        {"key": "neb_sparkle", "label": "Sparkle", "kind": "choice", "options": SPARKLE_LABELS},
        {"key": "neb_seed", "label": "Seed", "kind": "field", "integer": True},
    ]
    groups = [
        {"group": "Colour 1", "controls": _rgb("neb_c1")},
        {"group": "Colour 2", "controls": _rgb("neb_c2")},
        {"group": "Nebula", "controls": core},
    ]
    if advanced:
        groups += [
            {"group": "Colour 1 amplitude", "controls": _rgb("amp1")},
            {"group": "Colour 2 amplitude", "controls": _rgb("amp2")},
            {"group": "Colour 1 modulators", "controls": [
                {"key": f"mod1_{c}", "label": lbl, "kind": "choice", "options": MOD_LABELS}
                for c, lbl in zip("rgb", ("R field", "G field", "B field"))]},
            {"group": "Colour 2 modulators", "controls": [
                {"key": f"mod2_{c}", "label": lbl, "kind": "choice", "options": MOD_LABELS}
                for c, lbl in zip("rgb", ("R field", "G field", "B field"))]},
            {"group": "Structure", "controls": [
                {"key": "neb_sin_freq", "label": "Sine frequency", "kind": "slider", "min": 2.0, "max": 16.0, "step": 0.1},
                {"key": "neb_warp", "label": "Warp octaves", "kind": "slider", "min": 2, "max": 8, "integer": True},
                {"key": "neb_arm", "label": "Arm octaves", "kind": "slider", "min": 2, "max": 8, "integer": True},
            ]},
        ]
    return groups


def _clouds_groups():
    return [
        {"group": "Cloud colour", "controls": _rgb("cld_cloud")},
        {"group": "Sky colour", "controls": _rgb("cld_sky")},
        {"group": "Clouds", "controls": [
            {"key": "cld_sat", "label": "Saturation", "kind": "slider", "min": 0.0, "max": 2.0, "step": 0.05},
            {"key": "cld_seed", "label": "Seed", "kind": "field", "integer": True},
        ]},
    ]


def _smoke_layer_group(n):
    return {"group": f"Layer {n}", "controls": [
        {"key": f"smk_l{n}_opacity", "label": "Opacity ×", "kind": "slider", "min": 0.0, "max": 3.0, "step": 0.01},
        {"key": f"smk_l{n}_amount", "label": "Amount ×", "kind": "slider", "min": 0.0, "max": 3.0, "step": 0.01},
        {"key": f"smk_l{n}_stretch", "label": "Stretch ×", "kind": "slider", "min": 0.25, "max": 4.0, "step": 0.05},
        {"key": f"smk_l{n}_angle", "label": "Direction offset (deg)", "kind": "slider", "min": -90.0, "max": 90.0, "step": 1.0},
        {"key": f"smk_l{n}_soft", "label": "Extra softness", "kind": "slider", "min": 0, "max": 10, "integer": True},
    ]}


def _smoke_groups(advanced=False):
    return _smoke_base_groups() + (
        [_smoke_layer_group(n) for n in range(1, SMOKE_MAX_LAYERS + 1)] if advanced else [])


def _smoke_base_groups():
    return [
        {"group": "Smoke", "controls": [
            {"key": "smk_seed", "label": "Seed (composition)", "kind": "field", "integer": True},
            {"key": "smk_layers", "label": "Layers", "kind": "slider", "min": 1, "max": 12, "integer": True},
            {"key": "smk_amount", "label": "Smoke amount", "kind": "slider", "min": 0.03, "max": 0.6, "step": 0.01},
            {"key": "smk_opacity", "label": "Layer opacity", "kind": "slider", "min": 0.0, "max": 1.0, "step": 0.01},
            {"key": "smk_gamma", "label": "Core falloff", "kind": "slider", "min": 0.3, "max": 4.0, "step": 0.05},
            {"key": "smk_soft", "label": "Edge softness (1 = off)", "kind": "slider", "min": 1, "max": 12, "integer": True},
            {"key": "smk_op_var", "label": "Opacity variation (0 = all equal)", "kind": "slider", "min": 0.0, "max": 3.0, "step": 0.01},
        ]},
        {"group": "Wisps", "controls": [
            {"key": "smk_stretch_lo", "label": "Stretch, least", "kind": "slider", "min": 1.0, "max": 10.0, "step": 0.1},
            {"key": "smk_stretch_hi", "label": "Stretch, most", "kind": "slider", "min": 1.0, "max": 10.0, "step": 0.1},
            {"key": "smk_warp", "label": "Warp octaves", "kind": "slider", "min": 2, "max": 8, "integer": True},
            {"key": "smk_arm", "label": "Detail octaves", "kind": "slider", "min": 2, "max": 8, "integer": True},
            {"key": "smk_spread", "label": "Direction spread (0 = all one way)", "kind": "slider", "min": 0.0, "max": 2.0, "step": 0.01},
            {"key": "smk_rotate", "label": "Rotate all (deg)", "kind": "slider", "min": -180.0, "max": 180.0, "step": 1.0},
        ]},
        {"group": "Depth", "controls": [
            {"key": "smk_deep_soft", "label": "Deep layer softness (1 = off)", "kind": "slider", "min": 1, "max": 12, "integer": True},
            {"key": "smk_deep_op", "label": "Deep layer opacity", "kind": "slider", "min": 0.0, "max": 1.0, "step": 0.01},
            {"key": "smk_veil_soft", "label": "Body veil softness (1 = off)", "kind": "slider", "min": 1, "max": 12, "integer": True},
            {"key": "smk_shadow", "label": "Smoke shadow (0 = off)", "kind": "slider", "min": 0.0, "max": 1.0, "step": 0.01},
            {"key": "smk_shadow_soft", "label": "Shadow softness", "kind": "slider", "min": 1, "max": 32, "integer": True},
        ]},
        {"group": "Body (light)", "controls": _rgb("smk_light")},
        {"group": "Body (deep)", "controls": _rgb("smk_mid")},
        {"group": "Smoke ink", "controls": _rgb("smk_ink")},
        {"group": "Dark accents", "controls": [
            {"key": "smk_acc_count", "label": "Accent layers (0 = off)", "kind": "slider", "min": 0, "max": 8, "integer": True},
            {"key": "smk_acc_seed", "label": "Accent seed", "kind": "field", "integer": True},
            {"key": "smk_acc_amount", "label": "Amount (low = thin threads)", "kind": "slider", "min": 0.02, "max": 0.5, "step": 0.01},
            {"key": "smk_acc_opacity", "label": "Darkness", "kind": "slider", "min": 0.0, "max": 1.0, "step": 0.01},
            {"key": "smk_acc_gamma", "label": "Core falloff", "kind": "slider", "min": 0.3, "max": 4.0, "step": 0.05},
            {"key": "smk_acc_soft", "label": "Softness (1 = sharp)", "kind": "slider", "min": 1, "max": 12, "integer": True},
            {"key": "smk_acc_stretch_lo", "label": "Stretch, least", "kind": "slider", "min": 1.0, "max": 10.0, "step": 0.1},
            {"key": "smk_acc_stretch_hi", "label": "Stretch, most", "kind": "slider", "min": 1.0, "max": 10.0, "step": 0.1},
            {"key": "smk_acc_follow", "label": "Follow existing smoke (0 = anywhere)", "kind": "slider", "min": 0.0, "max": 1.0, "step": 0.01},
        ]},
        {"group": "Accent ink", "controls": _rgb("smk_acc_ink")},
    ]


# Vinyl Effects: finishes over any style, previewed here the way both apps apply them.
def _effect_key(effect_id):
    return "fx_" + effect_id.replace("-", "_")


_EFFECTS_GROUP = {"group": "Vinyl Effects", "controls": [
    *({"key": _effect_key(e), "label": label, "kind": "toggle"}
      for e, label in catalog.VINYL_EFFECTS.items()),
    {"key": "fx_grooves", "label": "Grooves", "kind": "choice",
     "options": list(catalog.GROOVE_TREATMENTS.values())},
]}


def effects_from(p):
    """The Vinyl Effects switched on in studio params."""
    return [e for e in catalog.VINYL_EFFECTS if float(p.get(_effect_key(e), 0)) >= 0.5]


def grooves_from(p):
    """The groove treatment chosen in studio params (an index into GROOVE_TREATMENTS)."""
    treatments = list(catalog.GROOVE_TREATMENTS)
    i = int(p.get("fx_grooves", 0))
    return treatments[i] if 0 <= i < len(treatments) else "auto"


def param_spec(family, advanced=False):
    if family == "mandelbrot":
        body = _mandel_groups()
    elif family == "color":
        body = [{"group": "Vinyl colour", "controls": _rgb("col")}]
    elif family == "nebula":
        body = _nebula_groups(advanced)
    elif family == "clouds":
        body = _clouds_groups()
    elif family == "smoke":
        body = _smoke_groups(advanced)
    else:
        body = []
    return body + [_EFFECTS_GROUP]


# --------------------------------------------------------------------- render

def _nebula_args(p, advanced):
    """The ``_nebula_palette`` arguments, saturation and structure a nebula's
    params describe (what a nebula style file stores)."""
    if advanced:
        amp1 = (p["amp1_r"], p["amp1_g"], p["amp1_b"])
        amp2 = (p["amp2_r"], p["amp2_g"], p["amp2_b"])
        mods1 = tuple(NEBULA_MODS[int(p[f"mod1_{c}"])] for c in "rgb")
        mods2 = tuple(NEBULA_MODS[int(p[f"mod2_{c}"])] for c in "rgb")
        sin_freq, warp, arm = p["neb_sin_freq"], int(p["neb_warp"]), int(p["neb_arm"])
    else:
        k = p["neb_contrast"]
        amp1 = tuple(k * a for a in DEFAULT_AMP1)
        amp2 = tuple(k * a for a in DEFAULT_AMP2)
        mods1, mods2 = ("t1", "hs", "sin"), ("t3", "t1", "inv_t3")
        sin_freq, warp, arm = 8.0, 6, 7
    return {
        "col1": (p["neb_c1_r"], p["neb_c1_g"], p["neb_c1_b"]),
        "col2": (p["neb_c2_r"], p["neb_c2_g"], p["neb_c2_b"]),
        "amp1": amp1, "amp2": amp2, "mods1": mods1, "mods2": mods2, "sin_freq": sin_freq,
        "bright": BRIGHT_MODES[int(p["neb_bright"])],
        "sparkle": SPARKLE_MODES[int(p["neb_sparkle"])],
        "saturation": float(p["neb_sat"]), "warp": warp, "arm": arm,
    }


def _nebula_palette_from(p, advanced):
    """Build the nebula palette closure + structure (warp, arm) from params."""
    a = _nebula_args(p, advanced)
    fn = _nebula_palette(a["col1"], a["col2"], a["amp1"], a["amp2"], a["mods1"], a["mods2"],
                         a["sin_freq"], a["bright"], a["sparkle"])
    return fn, a["warp"], a["arm"]


def _smoke_params(p):
    """Studio params -> the renderer's SMOKE_LAYER_PARAMS shape."""
    lo, hi = sorted((float(p["smk_stretch_lo"]), float(p["smk_stretch_hi"])))
    return {
        "layers": int(p["smk_layers"]), "opacity": float(p["smk_opacity"]),
        "amount": float(p["smk_amount"]), "gamma": float(p["smk_gamma"]),
        "soft": int(p["smk_soft"]), "stretch": (lo, hi),
        "warp_oct": int(p["smk_warp"]), "arm_oct": int(p["smk_arm"]),
        "deep_soft": int(p["smk_deep_soft"]), "deep_opacity": float(p["smk_deep_op"]),
        "veil_soft": int(p["smk_veil_soft"]),
        "light": tuple(int(p[f"smk_light_{c}"]) for c in "rgb"),
        "mid": tuple(int(p[f"smk_mid_{c}"]) for c in "rgb"),
        "ink": tuple(int(p[f"smk_ink_{c}"]) for c in "rgb"),
        "opacity_variation": float(p["smk_op_var"]), "spread": float(p["smk_spread"]),
        "rotate": float(p["smk_rotate"]),
        "accents": int(p["smk_acc_count"]), "accent_seed": int(p["smk_acc_seed"]),
        "accent_amount": float(p["smk_acc_amount"]), "accent_opacity": float(p["smk_acc_opacity"]),
        "accent_gamma": float(p["smk_acc_gamma"]), "accent_soft": int(p["smk_acc_soft"]),
        "accent_stretch": tuple(sorted((float(p["smk_acc_stretch_lo"]), float(p["smk_acc_stretch_hi"])))),
        "accent_follow": float(p["smk_acc_follow"]),
        "accent_ink": tuple(int(p[f"smk_acc_ink_{c}"]) for c in "rgb"),
        "shadow": float(p["smk_shadow"]), "shadow_soft": int(p["smk_shadow_soft"]),
        **{long: tuple((int if short == "soft" else float)(p[f"smk_l{n}_{short}"])
                       for n in range(1, SMOKE_MAX_LAYERS + 1))
           for short, long in _LAYER_TRIMS},
    }


def build_style(p, family, advanced):
    """Return the forced style dict, injecting any live catalog entries."""
    if family == "mandelbrot":
        interior = (int(p["int_r"]), int(p["int_g"]), int(p["int_b"]))
        fractals.MANDELBROT_COLORS[_LIVE_KEY] = (
            interior,
            (p["r_base"], p["r_amp"], p["r_freq"], p["r_phase"]),
            (p["g_base"], p["g_amp"], p["g_freq"], p["g_phase"]),
            (p["b_base"], p["b_amp"], p["b_freq"], p["b_phase"]))
        variant = (float(p["cx"]), float(p["cy"]), float(p["zoom"]),
                   int(p["max_iter"]), "studio", _LIVE_KEY)
        return {"type": "mandelbrot", "variant": variant}
    if family == "color":
        catalog.VINYL_COLORS[_LIVE_KEY] = (
            int(p["col_r"]), int(p["col_g"]), int(p["col_b"]))
        return {"type": "color", "color": _LIVE_KEY}
    if family == "nebula":
        fn, warp, arm = _nebula_palette_from(p, advanced)
        variant = (int(p["neb_seed"]), fn, "studio", float(p["neb_sat"]), warp, arm)
        return {"type": "nebula", "variant": variant}
    if family == "clouds":
        cloud = (p["cld_cloud_r"], p["cld_cloud_g"], p["cld_cloud_b"])
        sky = (p["cld_sky_r"], p["cld_sky_g"], p["cld_sky_b"])
        fn = _clouds_palette(cloud, sky)
        variant = (int(p["cld_seed"]), fn, "studio", float(p["cld_sat"]), 6, 7, "clouds")
        return {"type": "nebula", "variant": variant}
    if family == "smoke":
        variant = (int(p["smk_seed"]), None, "studio", 1.0, 5, 6, "layers", _smoke_params(p))
        return {"type": "nebula", "variant": variant}
    return {"type": family}        # black / clear


def _clear_live():
    fractals.MANDELBROT_COLORS.pop(_LIVE_KEY, None)
    catalog.VINYL_COLORS.pop(_LIVE_KEY, None)


def render_vinyl(p, family, advanced, size):
    """Render the full vinyl at the given radius. Returns
    (body_surf, grooves_surf, groove_blend, shine_surf)."""
    settings = VinylSettings(effects=effects_from(p), grooves=grooves_from(p))
    r = VinylRenderer(settings)
    style = build_style(p, family, advanced)
    try:
        r._current_album_path = _ALBUM
        r._current_override = settings.style
        r._current_vinyl_style = style

        body = r.build_record(size, _STUDIO_BOUNDARIES, _STUDIO_ALBUM_DUR,
                              album_path=_ALBUM)

        grooves, blend = r.build_grooves_overlay(size, style, _STUDIO_BOUNDARIES,
                                                 _STUDIO_ALBUM_DUR)

        shine = r.build_shine_overlay(size, style)
        return body, grooves, blend, shine
    finally:
        _clear_live()


# ------------------------------------------------------- guardrails + style files

# Families lp-studio can ship as a style file (lpcore/vinyl/styles).
SHIPPABLE = ("smoke", "clouds", "nebula")
_SEED_KEY = {"smoke": "smk_seed", "clouds": "cld_seed", "nebula": "neb_seed"}

# The params each family owns, so Reset leaves the other families alone.
_FAMILY_PREFIXES = {
    "mandelbrot": ("cx", "cy", "zoom", "max_iter", "int_", "r_", "g_", "b_"),
    "color": ("col_",),
    "nebula": ("neb_", "amp1_", "amp2_", "mod1_", "mod2_"),
    "clouds": ("cld_",),
    "smoke": ("smk_",),
}

# The smoke colour ramp (see lpcore.vinyl.ramp): the light body colour leads,
# and while the ramp is linked the three darker colours follow it.
_RAMP_PREFIX = {"light": "smk_light", "mid": "smk_mid", "ink": "smk_ink",
                "accent_ink": "smk_acc_ink"}
_RAMP_LABELS = {"light": "Body (light)", "mid": "Body (deep)", "ink": "Smoke ink",
                "accent_ink": "Accent ink"}
_LIGHT_KEYS = {f"smk_light_{c}" for c in "rgb"}
_DERIVED_KEYS = {f"{_RAMP_PREFIX[k]}_{c}" for k in ramp.RAMP for c in "rgb"}

# A per-layer trim at this value changes nothing (see SMOKE_LAYER_PARAMS).
_TRIM_UNTOUCHED = {"layer_opacity": 1.0, "layer_amount": 1.0, "layer_stretch": 1.0,
                   "layer_angle": 0.0, "layer_soft": 0}

_COALESCE_S = 0.4       # changes to one control this close together undo as one step
_HISTORY_LIMIT = 200


def _rgb_of(p, prefix):
    return tuple(int(p[f"{prefix}_{c}"]) for c in "rgb")


def _set_rgb(p, prefix, rgb):
    for c, v in zip("rgb", rgb):
        p[f"{prefix}_{c}"] = int(v)


def _hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(int(v) for v in rgb))


def ramp_colours(p):
    """{light, mid, ink, accent_ink} RGB tuples from smoke params."""
    return {k: _rgb_of(p, prefix) for k, prefix in _RAMP_PREFIX.items()}


def smoke_style_params(p):
    """Studio params -> a smoke style file's params: the renderer's keys, with
    per-layer trims cut to the layers that exist and change something."""
    out = _smoke_params(p)
    for key, untouched in _TRIM_UNTOUCHED.items():
        trims = list(out[key][:out["layers"]])
        while trims and trims[-1] == untouched:
            trims.pop()
        if trims:
            out[key] = tuple(trims)
        else:
            del out[key]
    return out


def studio_from_smoke(params):
    """A smoke style's renderer params -> studio params (the inverse of _smoke_params)."""
    P = {**SMOKE_LAYER_PARAMS, **params}
    s = {
        "smk_layers": P["layers"], "smk_opacity": P["opacity"], "smk_amount": P["amount"],
        "smk_gamma": P["gamma"], "smk_soft": P["soft"],
        "smk_stretch_lo": P["stretch"][0], "smk_stretch_hi": P["stretch"][1],
        "smk_warp": P["warp_oct"], "smk_arm": P["arm_oct"],
        "smk_deep_soft": P["deep_soft"], "smk_deep_op": P["deep_opacity"],
        "smk_veil_soft": P["veil_soft"], "smk_op_var": P["opacity_variation"],
        "smk_spread": P["spread"], "smk_rotate": P["rotate"],
        "smk_shadow": P["shadow"], "smk_shadow_soft": P["shadow_soft"],
        "smk_acc_count": P["accents"], "smk_acc_seed": P["accent_seed"],
        "smk_acc_amount": P["accent_amount"], "smk_acc_opacity": P["accent_opacity"],
        "smk_acc_gamma": P["accent_gamma"], "smk_acc_soft": P["accent_soft"],
        "smk_acc_stretch_lo": P["accent_stretch"][0], "smk_acc_stretch_hi": P["accent_stretch"][1],
        "smk_acc_follow": P["accent_follow"],
    }
    for key, prefix in _RAMP_PREFIX.items():
        _set_rgb(s, prefix, P[key])
    for short, long in _LAYER_TRIMS:
        seq = P[long]
        for n in range(1, SMOKE_MAX_LAYERS + 1):
            s[f"smk_l{n}_{short}"] = seq[n - 1] if n <= len(seq) else _TRIM_UNTOUCHED[long]
    return s


def studio_from_clouds(params):
    s = {"cld_sat": params["saturation"]}
    _set_rgb(s, "cld_cloud", params["cloud"])
    _set_rgb(s, "cld_sky", params["sky"])
    return s


def studio_from_nebula(params):
    """A nebula style's palette arguments -> studio params, in Advanced mode
    (the only mode that can hold every combination)."""
    s = {"neb_sat": params["saturation"], "neb_sin_freq": params["sin_freq"],
         "neb_warp": params["warp"], "neb_arm": params["arm"],
         "neb_bright": BRIGHT_MODES.index(params["bright"]),
         "neb_sparkle": SPARKLE_MODES.index(params["sparkle"])}
    _set_rgb(s, "neb_c1", params["col1"])
    _set_rgb(s, "neb_c2", params["col2"])
    for c, a1, a2, m1, m2 in zip("rgb", params["amp1"], params["amp2"],
                                 params["mods1"], params["mods2"]):
        s[f"amp1_{c}"], s[f"amp2_{c}"] = int(round(a1)), int(round(a2))
        s[f"mod1_{c}"], s[f"mod2_{c}"] = NEBULA_MODS.index(m1), NEBULA_MODS.index(m2)
    return s


def style_entry(p, family, advanced, name, order, ramp_linked=False):
    """The style file lp-studio writes for these params (see lpcore.vinyl.styles)."""
    if family == "smoke":
        params = smoke_style_params(p)
    elif family == "clouds":
        params = {"cloud": _rgb_of(p, "cld_cloud"), "sky": _rgb_of(p, "cld_sky"),
                  "saturation": float(p["cld_sat"])}
    elif family == "nebula":
        params = _nebula_args(p, advanced)
    else:
        raise ValueError(f"{family} styles are not style files")
    hints = {"effects": effects_from(p), "grooves": grooves_from(p)}
    if family == "smoke":
        hints["ramp_linked"] = bool(ramp_linked)
    return {"name": name, "family": family, "order": order, "seed": int(p[_SEED_KEY[family]]),
            "params": params, "studio": hints}


# ------------------------------------------------------------------ controller

class StudioController(QObject):
    """Everything QML edits: the family, its params, undo history, the colour
    ramp guardrails, saved templates and shipping a style file."""

    paramsChanged = Signal()
    familyChanged = Signal()
    advancedChanged = Signal()
    nameChanged = Signal()
    statusChanged = Signal()
    hqChanged = Signal()
    rampLinkedChanged = Signal()
    guardrailsChanged = Signal()
    contrastChanged = Signal()
    historyChanged = Signal()
    shippingChanged = Signal()

    def __init__(self, parent=None, clock=time.monotonic):
        super().__init__(parent)
        self._params = dict(DEFAULTS)
        self._family = "mandelbrot"
        self._advanced = False
        self._name = "untitled"
        self._status = ""
        self._hq = False
        self._ramp_linked = True
        self._contrast = None
        self._guardrails = []
        self._shipping = False
        self._process = None
        self._clock = clock
        self._history = [self._state()]
        self._hpos = 0
        self._last_change = (None, 0.0)
        self._saved = self._state()
        self._loaded_ref = None         # the template Save may overwrite without asking
        self.styles_root = None         # where shipped style files go (tests use a temp dir)
        self.launch_prerender = self._launch_prerender
        self.paramsChanged.connect(self._update_guardrails)
        self.familyChanged.connect(self._update_guardrails)
        self._update_guardrails()

    # --- family + advanced ---

    @Slot(result="QStringList")
    def families(self):
        return FAMILIES

    def getFamily(self):
        return self._family

    def setFamily(self, fam):
        if fam not in FAMILIES or fam == self._family:
            return
        self._family = fam
        self._set_contrast(None)
        self._record("family")
        self.familyChanged.emit()
        self.paramsChanged.emit()

    family = Property(str, getFamily, setFamily, notify=familyChanged)

    def getAdvanced(self):
        return self._advanced

    def setAdvanced(self, on):
        on = bool(on)
        if on != self._advanced:
            self._advanced = on
            self._record("advanced")
            self.advancedChanged.emit()
            self.paramsChanged.emit()

    advanced = Property(bool, getAdvanced, setAdvanced, notify=advancedChanged)

    # --- HQ preview (smoke renders are slow, so the default preview is small) ---

    def getHq(self):
        return self._hq

    def setHq(self, on):
        on = bool(on)
        if on != self._hq:
            self._hq = on
            self.hqChanged.emit()

    hq = Property(bool, getHq, setHq, notify=hqChanged)

    # --- params ---

    @Slot(result="QVariantList")
    def paramSpec(self):
        return param_spec(self._family, self._advanced)

    @Slot(str, result=float)
    def param(self, key):
        return float(self._params.get(key, 0.0))

    @Slot(str, float)
    def setParam(self, key, value):
        if key in _INTEGER_KEYS:
            value = int(round(value))
        if self._params.get(key) == value:
            return
        self._params[key] = value
        if self._family == "smoke" and self._ramp_linked:
            if key in _LIGHT_KEYS:
                self._apply_ramp()
            elif key in _DERIVED_KEYS:
                self._ramp_linked = False
                self.rampLinkedChanged.emit()
                self._set_status("Colour ramp unlinked: the darker colours are yours to tune")
        self._record(key)
        self.paramsChanged.emit()

    @Slot(str, result=str)
    def colorOf(self, prefix):
        """'#rrggbb' of an RGB param triple (``smk_light`` for smk_light_r/g/b)."""
        return _hex(_rgb_of(self._params, prefix))

    @Slot(str, str)
    def setColor(self, prefix, hex_color):
        """Set an RGB param triple from '#rrggbb' as one change (one undo step)."""
        text = (hex_color or "").strip().lstrip("#")
        if len(text) != 6:
            return
        try:
            rgb = tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return
        if _rgb_of(self._params, prefix) == rgb:
            return
        _set_rgb(self._params, prefix, rgb)
        if self._family == "smoke" and self._ramp_linked:
            if prefix == "smk_light":
                self._apply_ramp()
            elif f"{prefix}_r" in _DERIVED_KEYS:
                self._ramp_linked = False
                self.rampLinkedChanged.emit()
        self._record(prefix)
        self.paramsChanged.emit()

    def snapshot(self):
        return self._family, dict(self._params), self._advanced

    # --- colour ramp ---

    def _apply_ramp(self):
        derived = ramp.derive_ramp(_rgb_of(self._params, "smk_light"))
        for key, rgb in derived.items():
            _set_rgb(self._params, _RAMP_PREFIX[key], rgb)

    def getRampLinked(self):
        return self._ramp_linked

    def setRampLinked(self, on):
        on = bool(on)
        if on == self._ramp_linked:
            return
        self._ramp_linked = on
        if on and self._family == "smoke":
            self._apply_ramp()
            self._set_status("Colour ramp linked: body, smoke and accent colours follow the light colour")
        self._record("rampLinked")
        self.rampLinkedChanged.emit()
        self.paramsChanged.emit()

    rampLinked = Property(bool, getRampLinked, setRampLinked, notify=rampLinkedChanged)

    @Property("QVariantList", notify=guardrailsChanged)
    def rampSwatches(self):
        """light / mid / ink / accent: colour, brightness, and the brightness the ramp aims for."""
        colours = ramp_colours(self._params)
        light = ramp.luma(colours["light"])
        return [{"key": k, "prefix": _RAMP_PREFIX[k], "label": _RAMP_LABELS[k],
                 "color": _hex(rgb), "luma": round(ramp.luma(rgb)),
                 "target": round(light * ramp.RAMP.get(k, 1.0))}
                for k, rgb in colours.items()]

    # --- guardrails + contrast ---

    def _update_guardrails(self):
        issues = []
        if self._family == "smoke":
            c = ramp_colours(self._params)
            issues += ramp.check_ramp(c["light"], c["mid"], c["ink"], c["accent_ink"])
            issues += ramp.check_contrast(self._contrast)
        self._guardrails = [i.as_dict() for i in issues]
        self.guardrailsChanged.emit()

    @Property("QVariantList", notify=guardrailsChanged)
    def guardrails(self):
        return self._guardrails

    def _set_contrast(self, stats):
        self._contrast = stats
        self.contrastChanged.emit()

    def setContrast(self, stats):
        """Brightness spread of the latest preview render (from the preview item)."""
        self._set_contrast(stats)
        self._update_guardrails()

    @Property("QVariantMap", notify=contrastChanged)
    def contrast(self):
        return dict(self._contrast or {})

    # --- undo / redo ---

    def _state(self):
        return (self._family, self._advanced, self._ramp_linked,
                tuple(sorted(self._params.items())))

    def _record(self, key=None):
        state = self._state()
        if state == self._history[self._hpos]:
            return
        now = self._clock()
        last_key, last_time = self._last_change
        del self._history[self._hpos + 1:]
        if key is not None and key == last_key and now - last_time < _COALESCE_S and self._hpos > 0:
            self._history[self._hpos] = state
        else:
            self._history.append(state)
            del self._history[:-_HISTORY_LIMIT]
            self._hpos = len(self._history) - 1
        self._last_change = (key, now)
        self.historyChanged.emit()

    def _restore(self, state):
        family, advanced, linked, items = state
        family_changed = family != self._family
        advanced_changed = advanced != self._advanced
        linked_changed = linked != self._ramp_linked
        self._family, self._advanced, self._ramp_linked = family, advanced, linked
        self._params = dict(items)
        self._last_change = (None, 0.0)
        if family_changed:
            self._set_contrast(None)
            self.familyChanged.emit()
        if advanced_changed:
            self.advancedChanged.emit()
        if linked_changed:
            self.rampLinkedChanged.emit()
        self.paramsChanged.emit()
        self.historyChanged.emit()

    @Slot()
    def undo(self):
        if self._hpos > 0:
            self._hpos -= 1
            self._restore(self._history[self._hpos])

    @Slot()
    def redo(self):
        if self._hpos < len(self._history) - 1:
            self._hpos += 1
            self._restore(self._history[self._hpos])

    @Property(bool, notify=historyChanged)
    def canUndo(self):
        return self._hpos > 0

    @Property(bool, notify=historyChanged)
    def canRedo(self):
        return self._hpos < len(self._history) - 1

    @Property(bool, notify=historyChanged)
    def dirty(self):
        return self._state() != self._saved

    def _mark_saved(self):
        self._saved = self._state()
        self.historyChanged.emit()

    # --- name + status ---

    def getName(self):
        return self._name

    def setName(self, n):
        n = (n or "").strip()
        if n != self._name:
            self._name = n
            self.nameChanged.emit()

    name = Property(str, getName, setName, notify=nameChanged)

    def _set_status(self, msg):
        self._status = msg
        self.statusChanged.emit()

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    # --- mandelbrot seed presets ---

    @Slot(result="QStringList")
    def variantNames(self):
        return [f"{v[4]}-{v[5]}" for v in MANDELBROT_VARIANTS]

    @Slot(str)
    def loadVariant(self, spec):
        for v in MANDELBROT_VARIANTS:
            if f"{v[4]}-{v[5]}" == spec:
                cx, cy, zoom, max_iter, _name, color = v
                interior, r_p, g_p, b_p = catalog.MANDELBROT_COLORS[color][:4]
                self._params.update(
                    cx=cx, cy=cy, zoom=zoom, max_iter=max_iter,
                    int_r=interior[0], int_g=interior[1], int_b=interior[2],
                    r_base=r_p[0], r_amp=r_p[1], r_freq=r_p[2], r_phase=r_p[3],
                    g_base=g_p[0], g_amp=g_p[1], g_freq=g_p[2], g_phase=g_p[3],
                    b_base=b_p[0], b_amp=b_p[1], b_freq=b_p[2], b_phase=b_p[3])
                self.setName(spec)
                if self._family != "mandelbrot":
                    self._family = "mandelbrot"
                    self.familyChanged.emit()
                self._record("load")
                self.paramsChanged.emit()
                self._set_status(f"Loaded variant {spec}")
                return

    @Slot()
    def randomize(self):
        fam = self._family
        if fam == "mandelbrot":
            z = random.choice(MANDELBROT_ZOOMS)
            self._params.update(cx=z[0], cy=z[1], zoom=z[2], max_iter=z[3])
            for c in ("int_r", "int_g", "int_b"):
                self._params[c] = random.randint(0, 40)
            for ch in ("r", "g", "b"):
                self._params[f"{ch}_base"] = random.randint(0, 120)
                self._params[f"{ch}_amp"] = random.randint(60, 220)
                self._params[f"{ch}_freq"] = round(random.uniform(4.0, 14.0), 1)
                self._params[f"{ch}_phase"] = round(random.uniform(0.0, 6.28), 2)
            self._set_status("Randomized palette")
        elif fam == "color":
            for c in ("col_r", "col_g", "col_b"):
                self._params[c] = random.randint(20, 235)
            self._set_status("Randomized colour")
        elif fam == "nebula":
            for k in ("neb_c1_r", "neb_c1_g", "neb_c1_b",
                      "neb_c2_r", "neb_c2_g", "neb_c2_b"):
                self._params[k] = random.randint(0, 220)
            self._params["neb_seed"] = random.randint(1, 999)
            self._params["neb_bright"] = random.randint(0, 2)
            self._params["neb_sparkle"] = random.randint(0, 2)
            self._set_status("Randomized nebula")
        elif fam == "clouds":
            for k in ("cld_cloud_r", "cld_cloud_g", "cld_cloud_b"):
                self._params[k] = random.randint(170, 255)
            for k in ("cld_sky_r", "cld_sky_g", "cld_sky_b"):
                self._params[k] = random.randint(140, 240)
            self._params["cld_seed"] = random.randint(1, 999)
            self._set_status("Randomized clouds")
        elif fam == "smoke":
            # a new composition only: the look you tuned stays as it is
            self._params["smk_seed"] = random.randint(1, 9999)
            self._set_status(f"New smoke composition, seed {self._params['smk_seed']}")
        self._record("randomize")
        self.paramsChanged.emit()

    @Slot()
    def reset(self):
        prefixes = _FAMILY_PREFIXES.get(self._family, ())
        for k, v in DEFAULTS.items():
            if prefixes and k.startswith(prefixes):
                self._params[k] = v
        self._record("reset")
        self.paramsChanged.emit()
        self._set_status(f"Reset {self._family} to its defaults")

    # --- save / load local templates ---

    def _safe_name(self):
        name = self._name or "untitled"
        return "".join(c if (c.isalnum() or c in "-_") else "-" for c in name)

    def _template_ref(self):
        return f"{self._family}/{self._safe_name()}"

    @Slot(result=bool)
    def saveNeedsConfirm(self):
        """True when Save would replace a template other than the one loaded."""
        path = os.path.join(TEMPLATE_DIR, f"{self._template_ref()}.json")
        return os.path.isfile(path) and self._template_ref() != self._loaded_ref

    @Slot(result=str)
    def save(self):
        fam_dir = os.path.join(TEMPLATE_DIR, self._family)
        os.makedirs(fam_dir, exist_ok=True)
        path = os.path.join(fam_dir, f"{self._safe_name()}.json")
        with open(path, "w") as f:
            json.dump({"name": self._name or "untitled", "family": self._family,
                       "advanced": self._advanced, "ramp_linked": self._ramp_linked,
                       "params": self._params},
                      f, indent=2)
        self._loaded_ref = self._template_ref()
        self._mark_saved()
        self._set_status(f"Saved {path}")
        return path

    @Slot(result="QStringList")
    def savedTemplates(self):
        out = []
        if os.path.isdir(TEMPLATE_DIR):
            for fam in sorted(os.listdir(TEMPLATE_DIR)):
                d = os.path.join(TEMPLATE_DIR, fam)
                if os.path.isdir(d):
                    out += [f"{fam}/{f[:-5]}" for f in sorted(os.listdir(d))
                            if f.endswith(".json")]
        return out

    @Slot(str)
    def loadTemplate(self, ref):
        path = os.path.join(TEMPLATE_DIR, f"{ref}.json")
        if not os.path.isfile(path):
            return
        with open(path) as f:
            data = json.load(f)
        self._family = data.get("family", "mandelbrot")
        self._advanced = bool(data.get("advanced", False))
        self._params = dict(DEFAULTS)
        # keys from controls that no longer exist (the old shine sliders) are left behind
        self._params.update({k: v for k, v in data.get("params", {}).items() if k in DEFAULTS})
        linked = data.get("ramp_linked")
        if linked is None:
            # saved before the ramp could be linked: linked only if it already follows it
            c = ramp_colours(self._params)
            linked = ramp.matches_ramp(c["light"], c["mid"], c["ink"], c["accent_ink"])
        self._ramp_linked = bool(linked)
        self.setName(data.get("name", ref))
        self._loaded_ref = ref
        self._after_load(f"Loaded {ref}")

    @Slot(result="QStringList")
    def shippedStyles(self):
        return styles.names(root=self.styles_root)

    @Slot(str)
    def loadShipped(self, name):
        entry = next((e for e in styles.load(root=self.styles_root) if e["name"] == name), None)
        if entry is None:
            self._set_status(f"No shipped style named {name}")
            return
        family, params = entry["family"], styles.to_tuples(entry["params"])
        hints = entry.get("studio", {})
        self._params = dict(DEFAULTS)
        self._params[_SEED_KEY[family]] = entry["seed"]
        if family == "smoke":
            self._params.update(studio_from_smoke(params))
            self._advanced = any(k.startswith("layer_") for k in params)
            c = ramp_colours(self._params)
            self._ramp_linked = bool(hints.get("ramp_linked", ramp.matches_ramp(
                c["light"], c["mid"], c["ink"], c["accent_ink"])))
        elif family == "clouds":
            self._params.update(studio_from_clouds(params))
            self._advanced = False
        else:
            self._params.update(studio_from_nebula(params))
            self._advanced = True
        for effect in hints.get("effects", []):
            if effect in catalog.VINYL_EFFECTS:
                self._params[_effect_key(effect)] = 1
        treatments = list(catalog.GROOVE_TREATMENTS)
        if hints.get("grooves") in treatments:
            self._params["fx_grooves"] = treatments.index(hints["grooves"])
        self._family = family
        self.setName(name)
        self._loaded_ref = None
        self._after_load(f"Loaded shipped style {name}")

    def _after_load(self, message):
        self._set_contrast(None)
        self._record("load")
        self.familyChanged.emit()
        self.advancedChanged.emit()
        self.rampLinkedChanged.emit()
        self.paramsChanged.emit()
        self._mark_saved()
        self._set_status(message)

    # --- ship a style file ---

    def _code_style_names(self):
        """Nebula style names defined in fractals.py itself, which a file must not reuse."""
        return {v[2] for v in fractals.NEBULA_VARIANTS} - set(styles.names())

    @Slot(str, result="QVariantMap")
    def shipCheck(self, name):
        """What shipping under this name would do: {name, supported, valid, exists,
        builtin, issues, ok}. Guardrail issues are listed but do not block."""
        name = (name or "").strip()
        valid = styles.valid_name(name)
        exists = valid and os.path.isfile(styles.path_for(name, root=self.styles_root))
        builtin = name in self._code_style_names()
        supported = self._family in SHIPPABLE
        return {"name": name, "supported": supported, "valid": valid, "exists": bool(exists),
                "builtin": builtin, "issues": list(self._guardrails),
                "ok": supported and valid and not builtin}

    @Slot(str, result=str)
    def ship(self, name):
        check = self.shipCheck(name)
        name = check["name"]
        if not check["supported"]:
            self._set_status(f"{self._family.title()} styles can't be shipped as a style file yet")
            return ""
        if not check["valid"]:
            self._set_status("Style names are lowercase words joined by hyphens, like cobalt-marble")
            return ""
        if check["builtin"]:
            self._set_status(f"{name} is already a built-in style; pick another name")
            return ""
        existing = {e["name"]: e for e in styles.load(root=self.styles_root)}
        order = existing[name]["order"] if name in existing else styles.next_order(root=self.styles_root)
        entry = style_entry(self._params, self._family, self._advanced, name, order,
                            self._ramp_linked)
        path = styles.write(entry, root=self.styles_root)
        self.setName(name)
        self._set_shipping(True)
        self._set_status(f"Shipped {name}. Rendering its image (about a minute)...")
        self.launch_prerender(name)
        return path

    def _launch_prerender(self, name):
        proc = QProcess(self)
        proc.setWorkingDirectory(repo_dir())
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(lambda code, _status: self._prerender_finished(
            name, code, bytes(proc.readAll()).decode(errors="replace")))
        proc.start(sys.executable, ["-m", "lpcore.vinyl.prerender", "--only", name])
        self._process = proc

    def _prerender_finished(self, name, code, output):
        self._set_shipping(False)
        if code == 0:
            self._set_status(f"{name} is ready. Commit lpcore/vinyl/styles/nebula/{name}.json "
                             f"and lpcore/cache/nebula/{name}.png")
        else:
            lines = [ln for ln in output.strip().splitlines() if ln.strip()]
            self._set_status(f"Rendering {name} failed: {lines[-1] if lines else f'exit {code}'}")

    def _set_shipping(self, on):
        if on != self._shipping:
            self._shipping = on
            self.shippingChanged.emit()

    @Property(bool, notify=shippingChanged)
    def shipping(self):
        return self._shipping

    # --- compare + colour variations ---

    _variation_gen = 0
    _variations = ()

    @Slot(result="QVariantList")
    def compareStyles(self):
        """Rendered images of the catalog styles in this family, for the compare strip."""
        from PySide6.QtCore import QUrl

        from lpcore.vinyl.cache import CACHE_DIR, NEBULA_CACHE_DIR
        if self._family == "mandelbrot":
            items = [(f"{v[4]}-{v[5]}", CACHE_DIR) for v in MANDELBROT_VARIANTS]
        elif self._family in SHIPPABLE:
            route = {"layers": "smoke", "clouds": "clouds"}
            items = [(v[2], NEBULA_CACHE_DIR) for v in fractals.NEBULA_VARIANTS
                     if route.get(v[6] if len(v) > 6 else None, "nebula") == self._family]
        else:
            items = []
        shipped = set(styles.names())
        return [{"name": name, "url": QUrl.fromLocalFile(path).toString(), "shipped": name in shipped}
                for name, folder in items
                for path in [os.path.join(folder, f"{name}.png")] if os.path.isfile(path)]

    @Slot(int, result="QVariantList")
    def hueVariations(self, count):
        """This smoke look turned round the colour wheel: ``count`` light colours at the
        same brightness and saturation, each with its linked ramp. Thumbnails come from
        the ``variations`` image provider (lpstudio.variations)."""
        count = max(1, int(count))
        light = _rgb_of(self._params, "smk_light")
        hue, sat = ramp.hue_sat(light)
        sat = sat if sat >= 0.15 else 0.55      # a grey has no hue to turn
        lum = ramp.luma(light)
        base = _smoke_params(self._params)
        seed = int(self._params["smk_seed"])
        self._variation_gen += 1
        self._variations = []
        out = []
        for i in range(count):
            h = (hue + 360.0 * i / count) % 360.0
            colours = {"light": ramp.at_luma(h, sat, lum)}
            colours.update(ramp.derive_ramp(colours["light"]))
            variant = (seed, None, "variation", 1.0, 5, 6, "layers", {**base, **colours})
            self._variations.append((colours, variant))
            out.append({"index": i, "hue": round(h), "color": _hex(colours["light"]),
                        "source": f"image://variations/{self._variation_gen}/{i}"})
        return out

    def variation_job(self, gen, index):
        """The variant to render for image://variations/<gen>/<index>, or None if stale."""
        if gen != self._variation_gen or not 0 <= index < len(self._variations):
            return None
        return self._variations[index][1]

    @Slot(int)
    def applyVariation(self, index):
        if not 0 <= index < len(self._variations):
            return
        colours = self._variations[index][0]
        for key, rgb in colours.items():
            _set_rgb(self._params, _RAMP_PREFIX[key], rgb)
        was_linked, self._ramp_linked = self._ramp_linked, True
        self._record("variation")
        if not was_linked:
            self.rampLinkedChanged.emit()
        self.paramsChanged.emit()
        self._set_status(f"Using the {_hex(colours['light'])} variation (Ctrl+Z to go back)")

    # --- catalog snippet export ---

    @Slot(result=str)
    def catalogSnippet(self):
        p, name, fam = self._params, (self._name or "studio"), self._family

        if fam == "mandelbrot":
            interior = (int(p["int_r"]), int(p["int_g"]), int(p["int_b"]))

            def chan(ch):
                return (f"({int(p[ch + '_base'])}, {int(p[ch + '_amp'])}, "
                        f"{p[ch + '_freq']:.1f}, {p[ch + '_phase']:.2f})")
            return (
                "# MANDELBROT_ZOOMS (lpcore/vinyl/catalog.py):\n"
                f"    ({p['cx']:.6g}, {p['cy']:.6g}, {p['zoom']:.6g}, "
                f"{int(p['max_iter'])}, {name!r}),\n\n"
                "# MANDELBROT_COLORS: (interior, R, G, B):\n"
                f"    {name!r}: ({interior}, {chan('r')}, {chan('g')}, {chan('b')}),\n")

        if fam == "color":
            col = (int(p["col_r"]), int(p["col_g"]), int(p["col_b"]))
            return (
                "# VINYL_COLORS (lpcore/vinyl/catalog.py):\n"
                f"    {name!r}: {col},\n")

        if fam in SHIPPABLE:
            file_name = name if styles.valid_name(name) else "your-style-name"
            entry = style_entry(p, fam, self._advanced, file_name,
                                styles.next_order(root=self.styles_root), self._ramp_linked)
            return (f"// lpcore/vinyl/styles/nebula/{file_name}.json\n"
                    f"// Ship writes this file and renders its image for you.\n"
                    + styles.dumps(entry))

        return (f"# '{fam}' is a built-in style with no catalog entry to add.\n"
                f"# Nothing to export.\n")

    @Slot(str)
    def copyToClipboard(self, text):
        from PySide6.QtGui import QGuiApplication
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text)
            self._set_status("Snippet copied to clipboard")
