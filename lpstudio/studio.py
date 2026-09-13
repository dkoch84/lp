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

from PySide6.QtCore import Property, QObject, Signal, Slot

from lpcore.vinyl import catalog, fractals
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

def _nebula_palette_from(p, advanced):
    """Build the nebula palette closure + structure (warp, arm) from params."""
    c1 = (p["neb_c1_r"], p["neb_c1_g"], p["neb_c1_b"])
    c2 = (p["neb_c2_r"], p["neb_c2_g"], p["neb_c2_b"])
    bright = BRIGHT_MODES[int(p["neb_bright"])]
    sparkle = SPARKLE_MODES[int(p["neb_sparkle"])]
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
    fn = _nebula_palette(c1, c2, amp1, amp2, mods1, mods2, sin_freq, bright, sparkle)
    return fn, warp, arm


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


# ------------------------------------------------------------------ controller

class StudioController(QObject):
    paramsChanged = Signal()
    familyChanged = Signal()
    advancedChanged = Signal()
    nameChanged = Signal()
    statusChanged = Signal()
    hqChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._params = dict(DEFAULTS)
        self._family = "mandelbrot"
        self._advanced = False
        self._name = "untitled"
        self._status = ""
        self._hq = False

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
        self.familyChanged.emit()
        self.paramsChanged.emit()

    family = Property(str, getFamily, setFamily, notify=familyChanged)

    def getAdvanced(self):
        return self._advanced

    def setAdvanced(self, on):
        on = bool(on)
        if on != self._advanced:
            self._advanced = on
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
        self.paramsChanged.emit()

    def snapshot(self):
        return self._family, dict(self._params), self._advanced

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
                    self.setFamily("mandelbrot")
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
        self.paramsChanged.emit()

    @Slot()
    def reset(self):
        self._params = dict(DEFAULTS)
        self.paramsChanged.emit()
        self._set_status("Reset to defaults")

    # --- save / load local templates ---

    def _safe_name(self):
        name = self._name or "untitled"
        return "".join(c if (c.isalnum() or c in "-_") else "-" for c in name)

    @Slot(result=str)
    def save(self):
        fam_dir = os.path.join(TEMPLATE_DIR, self._family)
        os.makedirs(fam_dir, exist_ok=True)
        path = os.path.join(fam_dir, f"{self._safe_name()}.json")
        with open(path, "w") as f:
            json.dump({"name": self._name or "untitled", "family": self._family,
                       "advanced": self._advanced, "params": self._params},
                      f, indent=2)
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
        self.setName(data.get("name", ref))
        self.familyChanged.emit()
        self.advancedChanged.emit()
        self.paramsChanged.emit()
        self._set_status(f"Loaded {ref}")

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
                "# MANDELBROT_ZOOMS:\n"
                f"    ({p['cx']:.6g}, {p['cy']:.6g}, {p['zoom']:.6g}, "
                f"{int(p['max_iter'])}, {name!r}),\n\n"
                "# MANDELBROT_COLORS: (interior, R, G, B):\n"
                f"    {name!r}: ({interior}, {chan('r')}, {chan('g')}, {chan('b')}),\n")

        if fam == "color":
            col = (int(p["col_r"]), int(p["col_g"]), int(p["col_b"]))
            return (
                "# VINYL_COLORS:\n"
                f"    {name!r}: {col},\n")

        if fam == "smoke":
            return (
                "# NEBULA_VARIANTS (lpcore/vinyl/fractals.py). To change teal-marble,\n"
                "# replace its line with this one and keep the name 'teal-marble':\n"
                f"    ({int(p['smk_seed'])}, None, {name!r}, 1.0, 5, 6, 'layers',\n"
                f"     {_smoke_params(p)!r}),\n")

        if fam in ("nebula", "clouds"):
            if fam == "clouds":
                cloud = (int(p["cld_cloud_r"]), int(p["cld_cloud_g"]), int(p["cld_cloud_b"]))
                sky = (int(p["cld_sky_r"]), int(p["cld_sky_g"]), int(p["cld_sky_b"]))
                entry = (f"    ({int(p['cld_seed'])}, _clouds_palette({cloud}, {sky}), "
                         f"{name!r}, {p['cld_sat']:.2f}, 6, 7, 'clouds'),")
            else:
                c1 = (int(p["neb_c1_r"]), int(p["neb_c1_g"]), int(p["neb_c1_b"]))
                c2 = (int(p["neb_c2_r"]), int(p["neb_c2_g"]), int(p["neb_c2_b"]))
                fn, warp, arm = _nebula_palette_from(p, self._advanced)
                amp1 = (tuple(round(a) for a in (p["amp1_r"], p["amp1_g"], p["amp1_b"]))
                        if self._advanced
                        else tuple(round(p["neb_contrast"] * a) for a in DEFAULT_AMP1))
                amp2 = (tuple(round(a) for a in (p["amp2_r"], p["amp2_g"], p["amp2_b"]))
                        if self._advanced
                        else tuple(round(p["neb_contrast"] * a) for a in DEFAULT_AMP2))
                mods1 = (tuple(NEBULA_MODS[int(p[f"mod1_{c}"])] for c in "rgb")
                         if self._advanced else ("t1", "hs", "sin"))
                mods2 = (tuple(NEBULA_MODS[int(p[f"mod2_{c}"])] for c in "rgb")
                         if self._advanced else ("t3", "t1", "inv_t3"))
                freq = p["neb_sin_freq"] if self._advanced else 8.0
                entry = (
                    f"    ({int(p['neb_seed'])}, _nebula_palette({c1}, {c2}, {amp1}, {amp2},\n"
                    f"        mods1={mods1}, mods2={mods2}, sin_freq={freq:.1f}, "
                    f"bright={BRIGHT_MODES[int(p['neb_bright'])]!r}, "
                    f"sparkle={SPARKLE_MODES[int(p['neb_sparkle'])]!r}),\n"
                    f"     {name!r}, {p['neb_sat']:.2f}, {warp}, {arm}),")
            return (
                "# NEBULA_VARIANTS (lpcore/vinyl/fractals.py):\n"
                f"{entry}\n")

        return (f"# '{fam}' is a built-in style with no catalog entry to add.\n"
                f"# Nothing to export.\n")

    @Slot(str)
    def copyToClipboard(self, text):
        from PySide6.QtGui import QGuiApplication
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text)
            self._set_status("Snippet copied to clipboard")
