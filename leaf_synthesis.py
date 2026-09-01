"""High-quality species-aware procedural leaf/needle PBR synthesis.

This module replaces the original lightweight per-pixel leaf rasterizer with a
slower structural synthesizer.  Existing Trees 2.0 species/atlas layouts are
preserved (oak lobes, compound leaves, willow sprigs, conifer sprays, etc.), but
each blade or needle receives a coherent physical surface model:

* species-correct anti-aliased silhouettes
* primary and secondary venation / midribs
* convex blade curvature, edge roll and deterministic curl
* multi-scale chlorophyll mottling and fine surface variation
* serration, asymmetry, small damage and age variation
* normals derived from the final composite height field
* roughness derived from waxiness, veins, edges and microstructure
* a translucency/thickness-style map for thin-leaf shading/export

The implementation uses NumPy when available (standard Blender builds ship it).
If NumPy is missing, Trees 2.0 falls back to the previous atlas generator.
"""

import math
import random

try:
    import numpy as np
except Exception:  # pragma: no cover - Blender normally ships NumPy
    np = None

from . import procedural_pbr


_PREVIOUS_GENERATE_LEAF_ATLAS = None
_INSTALLED = False


QUALITY = {
    # Supersampling is per atlas cell.  Rendering one cell at a time prevents
    # the working set from scaling with the full supersampled atlas.
    "HIGH": 1,
    "ULTRA": 2,
    "EXTREME": 3,
}


STYLE_BY_SPECIES = {
    "GENERIC": "MESIC",
    "OAK": "MATTE_VEINED",
    "HOLM_OAK": "LEATHERY",
    "CORK_OAK": "LEATHERY",
    "BIRCH": "DELICATE",
    "BEECH": "MESIC",
    "MAPLE": "MATTE_VEINED",
    "ASH": "COMPOUND",
    "ELM": "ROUGH_VEINED",
    "LINDEN": "SOFT",
    "CHESTNUT": "ROUGH_VEINED",
    "WALNUT": "COMPOUND",
    "PLANE": "MATTE_VEINED",
    "ALDER": "SOFT",
    "ASPEN": "DELICATE",
    "POPLAR": "DELICATE",
    "WILLOW": "DELICATE_LANCE",
    "CHERRY": "SEMI_GLOSS",
    "APPLE": "MESIC",
    "MAGNOLIA": "THICK_GLOSSY",
    "JACARANDA": "FINE_COMPOUND",
    "EUCALYPTUS": "WAXY_LANCE",
    "OLIVE": "WAXY_LANCE",
    "ACACIA": "FINE_COMPOUND",
    "BAOBAB": "COMPOUND",
    "PINE": "NEEDLE_WAXY",
    "STONE_PINE": "NEEDLE_WAXY",
    "SPRUCE": "NEEDLE_MATTE",
    "FIR": "NEEDLE_WAXY",
    "CEDAR": "NEEDLE_MATTE",
    "CYPRESS": "SCALE_WAXY",
    "REDWOOD": "NEEDLE_MATTE",
    "DEAD_TREE": "NONE",
    "WINDSWEPT": "WEATHERED",
    "SAPLING": "SOFT",
}


STYLE = {
    "MESIC": dict(vein=1.00, micro=0.055, mottle=0.10, curl=0.055, edge_roll=0.045, translucency=0.73, wax=0.10),
    "MATTE_VEINED": dict(vein=1.18, micro=0.065, mottle=0.12, curl=0.050, edge_roll=0.050, translucency=0.68, wax=0.04),
    "LEATHERY": dict(vein=0.82, micro=0.040, mottle=0.075, curl=0.035, edge_roll=0.070, translucency=0.48, wax=0.34),
    "DELICATE": dict(vein=0.88, micro=0.040, mottle=0.085, curl=0.075, edge_roll=0.035, translucency=0.84, wax=0.04),
    "ROUGH_VEINED": dict(vein=1.25, micro=0.075, mottle=0.12, curl=0.055, edge_roll=0.050, translucency=0.66, wax=0.02),
    "SOFT": dict(vein=0.92, micro=0.045, mottle=0.10, curl=0.065, edge_roll=0.035, translucency=0.80, wax=0.03),
    "COMPOUND": dict(vein=0.90, micro=0.042, mottle=0.08, curl=0.050, edge_roll=0.038, translucency=0.76, wax=0.06),
    "FINE_COMPOUND": dict(vein=0.72, micro=0.030, mottle=0.065, curl=0.045, edge_roll=0.028, translucency=0.82, wax=0.03),
    "DELICATE_LANCE": dict(vein=0.78, micro=0.032, mottle=0.07, curl=0.060, edge_roll=0.030, translucency=0.84, wax=0.05),
    "SEMI_GLOSS": dict(vein=0.92, micro=0.040, mottle=0.08, curl=0.045, edge_roll=0.050, translucency=0.70, wax=0.22),
    "THICK_GLOSSY": dict(vein=0.75, micro=0.030, mottle=0.055, curl=0.030, edge_roll=0.075, translucency=0.43, wax=0.45),
    "WAXY_LANCE": dict(vein=0.70, micro=0.028, mottle=0.060, curl=0.045, edge_roll=0.065, translucency=0.56, wax=0.38),
    "NEEDLE_WAXY": dict(vein=0.30, micro=0.025, mottle=0.045, curl=0.025, edge_roll=0.080, translucency=0.36, wax=0.46),
    "NEEDLE_MATTE": dict(vein=0.30, micro=0.032, mottle=0.055, curl=0.030, edge_roll=0.070, translucency=0.42, wax=0.24),
    "SCALE_WAXY": dict(vein=0.18, micro=0.028, mottle=0.050, curl=0.022, edge_roll=0.055, translucency=0.34, wax=0.40),
    "WEATHERED": dict(vein=0.82, micro=0.085, mottle=0.18, curl=0.075, edge_roll=0.055, translucency=0.62, wax=0.00),
}


def _clamp01(value):
    return np.clip(value, 0.0, 1.0)


def _smooth01(value):
    value = _clamp01(value)
    return value * value * (3.0 - 2.0 * value)


def _smoothstep(lo, hi, value):
    if abs(float(hi) - float(lo)) < 1.0e-12:
        return (value >= hi).astype(np.float32)
    return _smooth01((value - lo) / (hi - lo))


def _style(species):
    return STYLE.get(STYLE_BY_SPECIES.get(str(species), "MESIC"), STYLE["MESIC"])


def _leaf_half_width(kind, v, profile):
    av = np.abs(v)
    inside = av < 1.0
    out = np.zeros_like(v, dtype=np.float32)

    if kind == "NEEDLE":
        out = 0.145 * np.maximum(0.0, 1.0 - av) ** 0.30
        return np.where(inside, np.maximum(0.018, out), 0.0).astype(np.float32)
    if kind == "LANCE":
        out = 0.78 * np.maximum(0.0, 1.0 - av ** 1.30) ** 0.58
        return np.where(inside, out, 0.0).astype(np.float32)
    if kind == "ROUND":
        out = np.sqrt(np.maximum(0.0, 1.0 - v * v))
        return np.where(inside, out, 0.0).astype(np.float32)
    if kind == "DELTOID":
        t = _clamp01((v + 1.0) * 0.5)
        out = np.clip(2.25 * (t ** 0.56) * ((1.0 - t) ** 0.78), 0.0, 1.0)
        return np.where(inside, out, 0.0).astype(np.float32)
    if kind == "HEART":
        base = np.sqrt(np.maximum(0.0, 1.0 - v * v))
        out = base * (1.0 + 0.18 * (1.0 - v) * 0.5)
        return np.where(inside, out, 0.0).astype(np.float32)

    base = np.maximum(0.0, 1.0 - av ** 1.70) ** 0.52
    if kind == "ELLIPTIC_POINTED":
        sharp = float(profile.get("tip_sharpness", 0.55))
        tip = 1.0 - sharp * 0.30 * _smoothstep(0.25, 0.95, v)
        out = base * tip
    elif kind == "OAK_LOBED":
        lobes = max(4, int(profile.get("lobes", 5)))
        depth = float(np.clip(profile.get("lobe_depth", 0.45), 0.0, 1.0))
        phase = (v + 0.82) * math.pi * max(2.0, lobes - 1.0)
        wave = 0.5 + 0.5 * np.cos(phase)
        out = base * (1.0 - depth * 0.50 * (1.0 - wave))
    else:
        out = base
    return np.where(inside, out, 0.0).astype(np.float32)


def _shape_alpha(kind, u, v, profile, detail, pixel_width):
    asymmetry = float(profile.get("asymmetry", 0.0))
    u = u + asymmetry * 0.16 * (1.0 - v * v)

    if kind == "PALMATE":
        r = np.sqrt((u * 0.96) ** 2 + (v * 0.94) ** 2)
        theta = np.arctan2(u, v)
        lobes = max(5, int(profile.get("lobes", 5)))
        depth = float(np.clip(profile.get("lobe_depth", 0.55), 0.0, 1.0))
        major = (0.5 + 0.5 * np.cos(lobes * theta)) ** 1.85
        boundary = (0.50 - depth * 0.08) + (0.28 + depth * 0.22) * major
        boundary += np.maximum(0.0, v) * 0.08
        alpha = _smoothstep(-pixel_width, pixel_width, boundary - r)
        return alpha.astype(np.float32), np.maximum(0.02, boundary).astype(np.float32)

    if kind == "SCALE":
        margin = 1.0 - (np.abs(u) * 1.10 + np.abs(v) * 0.92)
        alpha = _smoothstep(-pixel_width, pixel_width, margin)
        return alpha.astype(np.float32), np.ones_like(alpha, dtype=np.float32)

    half = _leaf_half_width(kind, v, profile)
    serr = float(profile.get("serration", 0.0)) * float(detail)
    if serr > 0.0 and kind not in {"NEEDLE", "SCALE"}:
        # Teeth are locked to the blade axis so their phase remains stable when
        # a leaf is rotated in the atlas. A second harmonic prevents a uniform
        # saw blade silhouette.
        teeth = 8.0 + 31.0 * min(1.0, serr)
        phase = (v + 1.0) * math.pi * teeth
        tooth = 0.62 * np.sin(phase) + 0.38 * np.sin(phase * 0.51 + 1.7)
        half *= 1.0 + serr * 0.10 * tooth

    margin = half - np.abs(u)
    alpha = _smoothstep(-pixel_width, pixel_width, margin)
    alpha *= _smoothstep(-pixel_width, pixel_width, 1.0 - np.abs(v))

    if kind == "HEART":
        notch_strength = float(profile.get("base_notch", 0.72))
        notch = np.exp(-((u / 0.18) ** 2 + ((v + 0.88) / 0.16) ** 2))
        alpha *= 1.0 - notch_strength * notch * (v < -0.45)

    return _clamp01(alpha).astype(np.float32), np.maximum(half, 0.02).astype(np.float32)


def _segment_distance(u, v, ax, ay, bx, by):
    vx = float(bx - ax)
    vy = float(by - ay)
    denom = vx * vx + vy * vy
    if denom <= 1.0e-10:
        return np.sqrt((u - ax) ** 2 + (v - ay) ** 2)
    t = np.clip(((u - ax) * vx + (v - ay) * vy) / denom, 0.0, 1.0)
    dx = u - (ax + vx * t)
    dy = v - (ay + vy * t)
    return np.sqrt(dx * dx + dy * dy)


def _vein_field(kind, u, v, half, style, detail):
    if kind in {"NEEDLE", "SCALE"}:
        mid = np.exp(-((u / 0.18) ** 2))
        return (mid * 0.72).astype(np.float32), mid.astype(np.float32)

    vein_gain = float(style["vein"]) * float(detail)
    mid_width = 0.030 + 0.012 / max(0.45, vein_gain)
    mid = np.exp(-((u / mid_width) ** 2)) * _smoothstep(-0.92, -0.70, v) * _smoothstep(0.98, 0.74, v)

    secondary = np.zeros_like(u, dtype=np.float32)
    # Primary secondary veins leave the midrib at progressively changing angles.
    positions = (-0.58, -0.34, -0.10, 0.14, 0.36, 0.56)
    for index, root_y in enumerate(positions):
        local_half = np.maximum(0.10, np.interp(root_y, [-1.0, 1.0], [0.72, 0.54]))
        length = 0.74 * local_half
        rise = 0.20 + index * 0.012
        for side in (-1.0, 1.0):
            dist = _segment_distance(u, v, 0.0, root_y, side * length, root_y + rise)
            width = 0.018 + 0.003 * abs(root_y)
            secondary = np.maximum(secondary, np.exp(-((dist / width) ** 2)))

    # Small tertiary vein texture is directional but intentionally subtle.
    tertiary = (
        0.5 + 0.5 * np.sin((u * 29.0 + v * 18.0) * math.pi + 0.7)
    ) * (
        0.5 + 0.5 * np.sin((u * -21.0 + v * 26.0) * math.pi + 2.1)
    )
    tertiary *= _smoothstep(0.02, 0.24, half - np.abs(u))

    field = _clamp01(mid + secondary * 0.58 + tertiary * 0.10 * min(1.5, vein_gain))
    return field.astype(np.float32), mid.astype(np.float32)


def _micro_pattern(u, v, seed):
    phase1 = (seed * 0.754877666) % (2.0 * math.pi)
    phase2 = (seed * 1.324717957) % (2.0 * math.pi)
    phase3 = (seed * 2.236067978) % (2.0 * math.pi)
    a = np.sin(u * 37.0 + v * 23.0 + phase1)
    b = np.sin(u * -19.0 + v * 43.0 + phase2)
    c = np.sin(u * 73.0 + v * 11.0 + phase3)
    return ((a * 0.48 + b * 0.34 + c * 0.18) * 0.5).astype(np.float32)


def _leaf_surface(kind, u, v, half, alpha, vein, midrib, profile, pbr, style, seed):
    # Normalized radial distance to the current edge works for asymmetric and
    # lobed shapes too, and therefore provides a coherent convex blade surface.
    radial = np.clip(np.abs(u) / np.maximum(half, 0.025), 0.0, 1.3)
    longitudinal = np.clip(np.abs(v), 0.0, 1.2)
    dome = np.maximum(0.0, 1.0 - radial ** 1.75) * np.maximum(0.0, 1.0 - longitudinal ** 2.2)

    edge_band = _smoothstep(0.64, 0.98, radial)
    curl_phase = ((seed * 0.618033989) % 1.0) * math.tau
    curl_sign = math.sin(curl_phase)
    curl = edge_band * (0.45 + 0.55 * np.sin(v * 3.2 + curl_phase)) * float(style["edge_roll"])
    curl += u * float(style["curl"]) * curl_sign * (1.0 - longitudinal * 0.35)

    micro = _micro_pattern(u, v, seed) * float(style["micro"]) * float(pbr.leaf_detail)
    vein_relief = vein * (0.060 * float(style["vein"]))
    mid_relief = midrib * (0.055 * float(style["vein"]))

    if kind == "NEEDLE":
        # Needles are closer to a rounded/keeled section than a flat blade.
        dome = np.maximum(0.0, 1.0 - radial ** 2.0) * 0.75
        curl *= 0.25
        vein_relief *= 0.35
    elif kind == "SCALE":
        dome = np.maximum(0.0, 1.0 - radial ** 1.4) * np.maximum(0.0, 1.0 - longitudinal ** 1.5) * 0.52
        curl *= 0.25
        vein_relief *= 0.20

    relief = dome * 0.105 + vein_relief + mid_relief + curl + micro
    relief *= alpha
    return relief.astype(np.float32), edge_band.astype(np.float32), micro.astype(np.float32)


def _leaf_color(kind, u, v, alpha, vein, edge_band, micro, profile, style, tone, seed):
    c1 = np.asarray(profile.get("leaf_color", (0.15, 0.40, 0.07)), dtype=np.float32)
    c2 = np.asarray(profile.get("leaf_color_2", (0.35, 0.60, 0.12)), dtype=np.float32)
    vein_color = np.asarray(profile.get("vein_color", (0.46, 0.64, 0.20)), dtype=np.float32)

    longitudinal = np.clip((v + 1.0) * 0.5, 0.0, 1.0)
    local_tone = np.clip(0.38 + longitudinal * 0.30 + float(tone) + micro * float(style["mottle"]), 0.0, 1.0)
    rgb = c1[None, None, :] + (c2 - c1)[None, None, :] * local_tone[..., None]

    # Veins are not simply bright lines; mix them toward the species vein color
    # and slightly lower saturation near the midrib.
    vein_mix = np.clip(vein * (0.18 + 0.12 * float(style["vein"])), 0.0, 0.42)[..., None]
    rgb = rgb * (1.0 - vein_mix) + vein_color[None, None, :] * vein_mix

    # Edge bleaching and mottling stop large cards from looking like flat blocks.
    edge_light = edge_band[..., None] * (0.025 + 0.035 * (1.0 - float(style["wax"])))
    rgb += edge_light

    if kind in {"NEEDLE", "SCALE"}:
        rgb *= 0.92 + 0.08 * (0.5 + 0.5 * micro[..., None])

    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def _damage_mask(u, v, alpha, profile, detail, seed):
    damage = float(profile.get("leaf_damage", 0.0)) * float(detail)
    if damage <= 0.0001:
        return alpha

    rng = random.Random(int(seed) ^ 0xD4A6E)
    result = alpha.copy()
    # Small edge bites and occasional interior holes. Keep defaults conservative.
    for _ in range(max(1, int(round(1 + damage * 5)))):
        hx = rng.uniform(-0.62, 0.62)
        hy = rng.uniform(-0.72, 0.72)
        radius = rng.uniform(0.035, 0.075) * (0.6 + damage * 2.0)
        hole = ((u - hx) ** 2 + (v - hy) ** 2) < radius * radius
        result = np.where(hole, result * (0.05 if rng.random() < 0.45 else 0.35), result)
    return result.astype(np.float32)


def _blend_property(dst, dst_alpha, src, src_alpha):
    out_alpha = src_alpha + dst_alpha * (1.0 - src_alpha)
    safe = np.maximum(out_alpha, 1.0e-6)
    if src.ndim == 3:
        weight = (src_alpha / safe)[..., None]
    else:
        weight = src_alpha / safe
    dst[...] = src * weight + dst * (1.0 - weight)
    dst_alpha[...] = out_alpha


def _render_leaf(cell, leaf, profile, pbr, style, seed, resolution_scale):
    cx = float(leaf["cx"])
    cy = float(leaf["cy"])
    angle = float(leaf["angle"])
    sx = max(0.004, float(leaf["sx"]))
    sy = max(0.004, float(leaf["sy"]))
    kind = str(leaf["shape"])

    ca = math.cos(angle)
    sa = math.sin(angle)
    extent_x = abs(ca) * sx + abs(sa) * sy
    extent_y = abs(sa) * sx + abs(ca) * sy

    size = cell["size"]
    # Cell coordinates are normalized to [-1, 1]. Pad for antialiasing and veins.
    pad = 3.5 / max(1.0, resolution_scale)
    px0 = max(0, int(math.floor(((cx - extent_x + 1.0) * 0.5) * size - pad)))
    px1 = min(size, int(math.ceil(((cx + extent_x + 1.0) * 0.5) * size + pad)))
    py0 = max(0, int(math.floor(((cy - extent_y + 1.0) * 0.5) * size - pad)))
    py1 = min(size, int(math.ceil(((cy + extent_y + 1.0) * 0.5) * size + pad)))
    if px1 <= px0 or py1 <= py0:
        return

    xs = ((np.arange(px0, px1, dtype=np.float32) + 0.5) / size) * 2.0 - 1.0
    ys = ((np.arange(py0, py1, dtype=np.float32) + 0.5) / size) * 2.0 - 1.0
    x, y = np.meshgrid(xs, ys)
    dx = x - cx
    dy = y - cy
    u = (ca * dx + sa * dy) / sx
    v = (-sa * dx + ca * dy) / sy

    pixel_width = 2.5 / max(16.0, min(sx, sy) * size)
    alpha, half = _shape_alpha(kind, u, v, profile, pbr.leaf_detail, pixel_width)
    alpha = _damage_mask(u, v, alpha, profile, pbr.leaf_detail, seed)
    if float(alpha.max()) <= 0.001:
        return

    vein, midrib = _vein_field(kind, u, v, half, style, pbr.leaf_detail)
    relief, edge_band, micro = _leaf_surface(kind, u, v, half, alpha, vein, midrib, profile, pbr, style, seed)
    rgb = _leaf_color(kind, u, v, alpha, vein, edge_band, micro, profile, style, leaf.get("tone", 0.0), seed)

    base_roughness = float(profile.get("leaf_roughness", 0.64))
    rough = base_roughness + micro * 0.055 + edge_band * 0.028 - vein * 0.035 - float(style["wax"]) * 0.16
    rough = np.clip(rough, 0.28, 0.94).astype(np.float32)

    # Higher values mean more light can pass through. Midribs and major veins are
    # optically thicker, while the thin blade between veins transmits more.
    trans = float(style["translucency"]) * (1.0 - vein * 0.38 - midrib * 0.22)
    trans *= 0.90 + 0.10 * (1.0 - edge_band)
    trans = np.clip(trans, 0.0, 1.0).astype(np.float32)

    dst_alpha = cell["alpha"][py0:py1, px0:px1]
    _blend_property(cell["rgb"][py0:py1, px0:px1], dst_alpha, rgb, alpha)
    # Relief is composited like a surface property; a small deterministic depth
    # bias keeps overlapping leaves visually separable without fake huge bumps.
    depth_bias = ((seed * 0.754877666) % 1.0) * 0.018
    _blend_property(cell["height"][py0:py1, px0:px1], dst_alpha, relief + depth_bias, alpha)
    _blend_property(cell["rough"][py0:py1, px0:px1], dst_alpha, rough, alpha)
    _blend_property(cell["trans"][py0:py1, px0:px1], dst_alpha, trans, alpha)


def _render_stems(cell, leaves, profile, pbr):
    if not leaves:
        return
    size = cell["size"]
    xs = ((np.arange(size, dtype=np.float32) + 0.5) / size) * 2.0 - 1.0
    ys = ((np.arange(size, dtype=np.float32) + 0.5) / size) * 2.0 - 1.0
    x, y = np.meshgrid(xs, ys)
    twig_color = np.asarray(profile.get("twig_color", (0.16, 0.09, 0.035)), dtype=np.float32)
    stem_alpha = np.zeros((size, size), dtype=np.float32)

    for leaf in leaves:
        angle = float(leaf["angle"])
        direction_x = math.sin(angle)
        direction_y = math.cos(angle)
        bx = float(leaf["cx"]) - direction_x * float(leaf["sy"]) * 0.72
        by = float(leaf["cy"]) - direction_y * float(leaf["sy"]) * 0.72
        ax = float(leaf.get("stem_x", 0.0))
        ay = float(leaf.get("stem_y", -0.72))

        vx = bx - ax
        vy = by - ay
        denom = vx * vx + vy * vy
        if denom <= 1.0e-10:
            continue
        t = np.clip(((x - ax) * vx + (y - ay) * vy) / denom, 0.0, 1.0)
        dx = x - (ax + vx * t)
        dy = y - (ay + vy * t)
        distance = np.sqrt(dx * dx + dy * dy)
        width = 0.0065 + 0.65 / max(size, 64)
        a = 1.0 - _smoothstep(width * 0.62, width * 1.35, distance)
        stem_alpha = np.maximum(stem_alpha, a.astype(np.float32))

    if float(stem_alpha.max()) <= 0.001:
        return

    # Place stems below blades in the composite. Only pixels not already mostly
    # covered by leaves receive the full stem contribution.
    visible = stem_alpha * (1.0 - cell["alpha"] * 0.82)
    old_alpha = cell["alpha"].copy()
    out_alpha = visible + old_alpha * (1.0 - visible)
    safe = np.maximum(out_alpha, 1.0e-6)
    weight = (visible / safe)[..., None]
    cell["rgb"] = twig_color[None, None, :] * weight + cell["rgb"] * (1.0 - weight)
    weight_s = visible / safe
    cell["height"] = 0.058 * weight_s + cell["height"] * (1.0 - weight_s)
    cell["rough"] = 0.82 * weight_s + cell["rough"] * (1.0 - weight_s)
    cell["trans"] = 0.05 * weight_s + cell["trans"] * (1.0 - weight_s)
    cell["alpha"] = out_alpha


def _normal_from_height(height, alpha, pbr, profile):
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    profile_strength = float(profile.get("leaf_normal_strength", 0.34))
    profile_factor = np.clip(profile_strength / 0.34, 0.45, 1.65)
    strength = 10.5 * float(pbr.leaf_normal_strength) * float(profile_factor)
    guard = _smoothstep(0.18, 0.82, alpha)
    nx = -dx * strength * guard
    ny = -dy * strength * guard
    nz = np.ones_like(height, dtype=np.float32)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.empty((height.shape[0], height.shape[1], 3), dtype=np.float32)
    normal[..., 0] = nx * inv * 0.5 + 0.5
    normal[..., 1] = ny * inv * 0.5 + 0.5
    normal[..., 2] = nz * inv * 0.5 + 0.5
    normal[alpha <= 0.001] = (0.5, 0.5, 1.0)
    return normal


def _downsample(field, factor):
    if factor <= 1:
        return field
    h, w = field.shape[:2]
    h2 = h // factor
    w2 = w // factor
    cropped = field[:h2 * factor, :w2 * factor]
    if field.ndim == 2:
        return cropped.reshape(h2, factor, w2, factor).mean(axis=(1, 3)).astype(np.float32)
    channels = field.shape[2]
    return cropped.reshape(h2, factor, w2, factor, channels).mean(axis=(1, 3)).astype(np.float32)


def _render_variant(profile, pbr, leaves, species, seed, cell_size, supersample):
    size = int(cell_size * supersample)
    cell = {
        "size": size,
        "alpha": np.zeros((size, size), dtype=np.float32),
        "rgb": np.zeros((size, size, 3), dtype=np.float32),
        "height": np.zeros((size, size), dtype=np.float32),
        "rough": np.full((size, size), float(profile.get("leaf_roughness", 0.64)), dtype=np.float32),
        "trans": np.zeros((size, size), dtype=np.float32),
    }
    style = _style(species)

    # Stems are logically behind blades. Rendering them first gives connected
    # compound leaves and willow sprigs without covering the leaf surfaces.
    _render_stems(cell, leaves, profile, pbr)
    for index, leaf in enumerate(leaves):
        _render_leaf(cell, leaf, profile, pbr, style, seed + index * 1009, size / 512.0)

    normal = _normal_from_height(cell["height"], cell["alpha"], pbr, profile)
    if supersample > 1:
        alpha = _downsample(cell["alpha"], supersample)
        rgb_premult = _downsample(cell["rgb"] * cell["alpha"][..., None], supersample)
        safe = np.maximum(alpha[..., None], 1.0e-6)
        rgb = np.where(alpha[..., None] > 1.0e-5, rgb_premult / safe, 0.0).astype(np.float32)
        normal = _downsample(normal, supersample)
        # Renormalize after filtering normal vectors in encoded 0..1 space.
        vec = normal * 2.0 - 1.0
        inv = 1.0 / np.maximum(np.sqrt((vec * vec).sum(axis=2, keepdims=True)), 1.0e-6)
        normal = np.clip(vec * inv * 0.5 + 0.5, 0.0, 1.0).astype(np.float32)
        rough = _downsample(cell["rough"], supersample)
        trans = _downsample(cell["trans"], supersample)
        height = _downsample(cell["height"], supersample)
    else:
        alpha = cell["alpha"]
        rgb = cell["rgb"]
        rough = cell["rough"]
        trans = cell["trans"]
        height = cell["height"]

    return {
        "alpha": np.clip(alpha, 0.0, 1.0).astype(np.float32),
        "rgb": np.clip(rgb, 0.0, 1.0).astype(np.float32),
        "normal": np.clip(normal, 0.0, 1.0).astype(np.float32),
        "rough": np.clip(rough, 0.0, 1.0).astype(np.float32),
        "trans": np.clip(trans, 0.0, 1.0).astype(np.float32),
        "height": height.astype(np.float32),
    }


def _write_image(name, rgba, filepath, non_color, pack):
    old = procedural_pbr.bpy.data.images.get(name)
    if old:
        procedural_pbr.bpy.data.images.remove(old, do_unlink=True)
    height, width = rgba.shape[:2]
    image = procedural_pbr.bpy.data.images.new(name=name, width=width, height=height, alpha=True, float_buffer=False)
    image.pixels.foreach_set(np.ascontiguousarray(rgba, dtype=np.float32).reshape(-1))
    if non_color:
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
    image.filepath_raw = str(filepath)
    image.file_format = "PNG"
    image["trees2_generated_pbr"] = True
    image["trees2_leaf_synthesis"] = "high_fidelity"
    image.save()
    if pack:
        try:
            image.pack()
        except Exception:
            pass
    return image


def _generate_leaf_atlas_hq(profile, pbr, seed, species, output):
    if np is None:
        return _PREVIOUS_GENERATE_LEAF_ATLAS(profile, pbr, seed, species, output)

    resolution = int(pbr.leaf_resolution)
    grid = max(1, int(pbr.atlas_grid))
    cell_size = max(16, resolution // grid)
    # Keep atlas dimensions exactly divisible by the grid. The UI resolutions
    # are powers of two by default, but this also makes custom values safe.
    final_resolution = cell_size * grid
    quality = str(getattr(pbr, "leaf_quality", "ULTRA"))
    supersample = QUALITY.get(quality, 2)

    albedo = np.zeros((final_resolution, final_resolution, 4), dtype=np.float32)
    normal = np.zeros((final_resolution, final_resolution, 4), dtype=np.float32)
    normal[..., :3] = (0.5, 0.5, 1.0)
    normal[..., 3] = 1.0
    roughness = np.ones((final_resolution, final_resolution, 4), dtype=np.float32)
    translucency = np.zeros((final_resolution, final_resolution, 4), dtype=np.float32)
    translucency[..., 3] = 1.0

    rng = random.Random(int(seed) ^ 0x4C454146)  # 'LEAF'
    for row in range(grid):
        for col in range(grid):
            variant = row * grid + col
            variant_rng = random.Random(rng.randrange(2**31) ^ (variant * 0x9E3779B1))
            # Use the current patched layout function so willow_foliage_fix and
            # foliage_atlas_assembly remain authoritative for cluster topology.
            leaves = procedural_pbr._variant_leaves(profile, variant_rng)
            rendered = _render_variant(
                profile,
                pbr,
                leaves,
                species,
                int(seed) + variant * 104729,
                cell_size,
                supersample,
            )

            y0 = (grid - 1 - row) * cell_size
            y1 = y0 + cell_size
            x0 = col * cell_size
            x1 = x0 + cell_size

            albedo[y0:y1, x0:x1, :3] = rendered["rgb"]
            albedo[y0:y1, x0:x1, 3] = rendered["alpha"]
            normal[y0:y1, x0:x1, :3] = rendered["normal"]
            roughness[y0:y1, x0:x1, 0] = rendered["rough"]
            roughness[y0:y1, x0:x1, 1] = rendered["rough"]
            roughness[y0:y1, x0:x1, 2] = rendered["rough"]
            roughness[y0:y1, x0:x1, 3] = 1.0
            translucency[y0:y1, x0:x1, 0] = rendered["trans"]
            translucency[y0:y1, x0:x1, 1] = rendered["trans"]
            translucency[y0:y1, x0:x1, 2] = rendered["trans"]
            translucency[y0:y1, x0:x1, 3] = rendered["alpha"]

    stem = f"trees2_{procedural_pbr._safe_name(species)}_{seed}_leaf"
    return {
        "albedo": _write_image(
            f"{stem}_albedo", albedo, output / f"{stem}_albedo.png", False, pbr.pack_images
        ),
        "normal": _write_image(
            f"{stem}_normal", normal, output / f"{stem}_normal.png", True, pbr.pack_images
        ),
        "roughness": _write_image(
            f"{stem}_roughness", roughness, output / f"{stem}_roughness.png", True, pbr.pack_images
        ),
        "translucency": _write_image(
            f"{stem}_translucency", translucency, output / f"{stem}_translucency.png", True, pbr.pack_images
        ),
    }


def install():
    global _PREVIOUS_GENERATE_LEAF_ATLAS, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE_LEAF_ATLAS = procedural_pbr._generate_leaf_atlas
    procedural_pbr._generate_leaf_atlas = _generate_leaf_atlas_hq
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    procedural_pbr._generate_leaf_atlas = _PREVIOUS_GENERATE_LEAF_ATLAS
    _INSTALLED = False
