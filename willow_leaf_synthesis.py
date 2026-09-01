"""Dedicated high-detail willow leaf rendering."""

from array import array
import math
import numpy as np

from . import leaf_synthesis, pbr_profiles, procedural_pbr

_PREVIOUS = {}
_OLD_PROFILE = {}
_OLD_STYLE = {}
_INSTALLED = False


def _is_willow(profile):
    return str(profile.get("arrangement", "")) == "WEEPING_SPRIG"


def _segment_distance(u, v, ax, ay, bx, by):
    vx, vy = float(bx - ax), float(by - ay)
    denom = vx * vx + vy * vy
    if denom <= 1.0e-10:
        return np.sqrt((u - ax) ** 2 + (v - ay) ** 2)
    t = np.clip(((u - ax) * vx + (v - ay) * vy) / denom, 0.0, 1.0)
    return np.sqrt((u - (ax + vx * t)) ** 2 + (v - (ay + vy * t)) ** 2)


def _willow_veins(u, v, half, detail):
    mid = np.exp(-((u / 0.021) ** 2))
    mid *= leaf_synthesis._smoothstep(-0.96, -0.76, v)
    mid *= leaf_synthesis._smoothstep(0.99, 0.82, v)
    secondary = np.zeros_like(u, dtype=np.float32)
    for root_y in (-0.72, -0.55, -0.38, -0.21, -0.04, 0.13, 0.30, 0.47, 0.63, 0.76):
        av = abs(root_y)
        local_half = 0.78 * max(0.0, 1.0 - av ** 1.30) ** 0.58
        lateral = max(0.075, local_half * (0.72 - av * 0.10))
        rise = 0.075 + 0.035 * (1.0 - av)
        for side in (-1.0, 1.0):
            dist = _segment_distance(u, v, 0.0, root_y, side * lateral, min(0.92, root_y + rise))
            secondary = np.maximum(secondary, np.exp(-((dist / (0.0105 + 0.0025 * av)) ** 2)))
    tertiary = (0.5 + 0.5 * np.sin((u * 33.0 + v * 15.0) * math.pi + 0.8))
    tertiary *= (0.5 + 0.5 * np.sin((u * -29.0 + v * 18.0) * math.pi + 2.0))
    tertiary *= leaf_synthesis._smoothstep(0.035, 0.20, half - np.abs(u))
    vein = np.clip(mid * 0.96 + secondary * 0.76 * float(detail) + tertiary * 0.09, 0.0, 1.0)
    return vein.astype(np.float32), mid.astype(np.float32)


def _willow_surface(u, v, half, alpha, vein, midrib, pbr, seed):
    radial = np.clip(np.abs(u) / np.maximum(half, 0.020), 0.0, 1.35)
    longitudinal = np.clip(np.abs(v), 0.0, 1.2)
    dome = np.maximum(0.0, 1.0 - radial ** 1.55) * np.maximum(0.0, 1.0 - longitudinal ** 2.55)
    edge = leaf_synthesis._smoothstep(0.66, 0.985, radial)
    phase = ((seed * 0.618033989) % 1.0) * math.tau
    micro_a = leaf_synthesis._micro_pattern(u, v, seed)
    micro_b = leaf_synthesis._micro_pattern(u * 1.37 + 0.11, v * 0.83 - 0.07, seed + 173)
    micro = (micro_a * 0.67 + micro_b * 0.33) * 0.078 * float(pbr.leaf_detail)
    corrugation = np.sin(v * 24.0 + u * 7.0 + phase) * np.sin(v * 8.5 - u * 13.0 + phase * 0.47)
    corrugation *= 0.010 * np.maximum(0.0, 1.0 - radial)
    edge_roll = edge * (0.45 + 0.55 * np.sin(v * 4.1 + phase)) * 0.052
    cross_camber = u * (0.018 + 0.010 * math.sin(phase)) * (1.0 - longitudinal * 0.42)
    secondary = np.maximum(0.0, vein - midrib)
    relief = dome * 0.145 + midrib * 0.086 + secondary * 0.040 + edge_roll + cross_camber + corrugation + micro
    return (relief * alpha).astype(np.float32), edge.astype(np.float32), micro.astype(np.float32)


def _sat(color, amount):
    c = np.asarray(color, dtype=np.float32)
    lum = float(c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722)
    return np.clip(lum + (c - lum) * amount, 0.0, 1.0)


def _willow_color(u, v, half, vein, edge, micro, profile, tone, seed):
    dark = _sat(profile.get("leaf_color", (0.105, 0.385, 0.045)), 1.30) * np.asarray((0.88, 0.96, 0.86))
    light = _sat(profile.get("leaf_color_2", (0.40, 0.70, 0.145)), 1.34) * np.asarray((1.04, 1.10, 0.98))
    vein_color = _sat(profile.get("vein_color", (0.53, 0.74, 0.22)), 1.18)
    radial = np.clip(np.abs(u) / np.maximum(half, 0.025), 0.0, 1.2)
    longitudinal = np.clip((v + 1.0) * 0.5, 0.0, 1.0)
    phase = ((seed * 0.41421356237) % 1.0) * math.tau
    mottle = 0.50 + 0.28 * np.sin(v * 7.1 + u * 3.4 + phase) + 0.22 * np.sin(v * 13.6 - u * 8.3 + phase * 1.71)
    mottle = np.clip(mottle, 0.0, 1.0)
    tissue = np.clip(0.24 + longitudinal * 0.18 + (1.0 - radial) * 0.17 + mottle * 0.25 + float(tone) * 0.55 + micro * 1.65, 0.0, 1.0)
    rgb = dark[None, None, :] + (light - dark)[None, None, :] * tissue[..., None]
    vm = np.clip(vein * 0.30, 0.0, 0.38)[..., None]
    rgb = rgb * (1.0 - vm) + vein_color[None, None, :] * vm
    rgb += edge[..., None] * np.asarray((0.020, 0.032, 0.010), dtype=np.float32)
    rgb *= 0.91 + 0.17 * mottle[..., None]
    lum = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    rgb = lum[..., None] + (rgb - lum[..., None]) * 1.13
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def _render_leaf(cell, leaf, profile, pbr, style, seed, resolution_scale):
    if not _is_willow(profile):
        return _PREVIOUS["render_leaf"](cell, leaf, profile, pbr, style, seed, resolution_scale)
    cx, cy, angle = float(leaf["cx"]), float(leaf["cy"]), float(leaf["angle"])
    sx, sy = max(0.004, float(leaf["sx"])), max(0.004, float(leaf["sy"]))
    ca, sa = math.cos(angle), math.sin(angle)
    ex, ey = abs(ca) * sx + abs(sa) * sy, abs(sa) * sx + abs(ca) * sy
    size = cell["size"]
    pad = 3.5 / max(1.0, resolution_scale)
    x0 = max(0, int(math.floor(((cx - ex + 1.0) * 0.5) * size - pad)))
    x1 = min(size, int(math.ceil(((cx + ex + 1.0) * 0.5) * size + pad)))
    y0 = max(0, int(math.floor(((cy - ey + 1.0) * 0.5) * size - pad)))
    y1 = min(size, int(math.ceil(((cy + ey + 1.0) * 0.5) * size + pad)))
    if x1 <= x0 or y1 <= y0:
        return
    xs = ((np.arange(x0, x1, dtype=np.float32) + 0.5) / size) * 2.0 - 1.0
    ys = ((np.arange(y0, y1, dtype=np.float32) + 0.5) / size) * 2.0 - 1.0
    x, y = np.meshgrid(xs, ys)
    dx, dy = x - cx, y - cy
    u = (ca * dx + sa * dy) / sx
    v = (-sa * dx + ca * dy) / sy
    pixel_width = 2.5 / max(16.0, min(sx, sy) * size)
    alpha, half = leaf_synthesis._shape_alpha(str(leaf["shape"]), u, v, profile, pbr.leaf_detail, pixel_width)
    alpha = leaf_synthesis._damage_mask(u, v, alpha, profile, pbr.leaf_detail, seed)
    if float(alpha.max()) <= 0.001:
        return
    vein, midrib = _willow_veins(u, v, half, pbr.leaf_detail)
    relief, edge, micro = _willow_surface(u, v, half, alpha, vein, midrib, pbr, seed)
    rgb = _willow_color(u, v, half, vein, edge, micro, profile, leaf.get("tone", 0.0), seed)
    rough = np.clip(float(profile.get("leaf_roughness", 0.61)) + micro * 0.08 + edge * 0.035 - vein * 0.045, 0.34, 0.88).astype(np.float32)
    trans = np.clip(0.88 * (1.0 - vein * 0.40 - midrib * 0.24) * (0.92 + 0.08 * (1.0 - edge)), 0.0, 1.0).astype(np.float32)
    dst = cell["alpha"][y0:y1, x0:x1]
    out = alpha + dst * (1.0 - alpha)
    safe = np.maximum(out, 1.0e-6)
    nw, ow = alpha / safe, dst * (1.0 - alpha) / safe
    cell["rgb"][y0:y1, x0:x1] = rgb * nw[..., None] + cell["rgb"][y0:y1, x0:x1] * ow[..., None]
    cell["height"][y0:y1, x0:x1] = (relief + ((seed * 0.754877666) % 1.0) * 0.012) * nw + cell["height"][y0:y1, x0:x1] * ow
    cell["rough"][y0:y1, x0:x1] = rough * nw + cell["rough"][y0:y1, x0:x1] * ow
    cell["trans"][y0:y1, x0:x1] = trans * nw + cell["trans"][y0:y1, x0:x1] * ow
    dst[...] = out


def _normal_from_height(height, alpha, pbr, profile):
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5
    pf = np.clip(float(profile.get("leaf_normal_strength", 0.34)) / 0.34, 0.45, 1.85)
    scale = max(0.50, min(height.shape) / 512.0)
    strength = 10.5 * scale * float(pbr.leaf_normal_strength) * float(pf) * (1.38 if _is_willow(profile) else 1.0)
    guard = leaf_synthesis._smoothstep(0.16, 0.80, alpha)
    nx, ny, nz = -dx * strength * guard, -dy * strength * guard, np.ones_like(height)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack((nx * inv * 0.5 + 0.5, ny * inv * 0.5 + 0.5, nz * inv * 0.5 + 0.5), axis=2).astype(np.float32)
    normal[alpha <= 0.001] = (0.5, 0.5, 1.0)
    return normal


def _write_image(name, rgba, filepath, non_color, pack):
    h, w = rgba.shape[:2]
    image = procedural_pbr._new_image(name, w, h, array("f", np.ascontiguousarray(rgba, dtype=np.float32).reshape(-1)), filepath, bool(non_color), bool(pack))
    image["trees2_leaf_synthesis"] = "WILLOW_DETAIL_V2" if "willow" in name.lower() else "HIGH_FIDELITY_V2"
    return image


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS["render_leaf"] = leaf_synthesis._render_leaf
    _PREVIOUS["normal"] = leaf_synthesis._normal_from_height
    _PREVIOUS["write"] = leaf_synthesis._write_image
    leaf_synthesis._render_leaf = _render_leaf
    leaf_synthesis._normal_from_height = _normal_from_height
    leaf_synthesis._write_image = _write_image
    profile = pbr_profiles.SPECIES_PBR.get("WILLOW")
    if profile:
        for key in ("leaf_color", "leaf_color_2", "vein_color", "leaf_normal_strength", "leaf_roughness"):
            _OLD_PROFILE[key] = profile.get(key)
        profile.update(leaf_color=(0.105, 0.385, 0.045), leaf_color_2=(0.40, 0.70, 0.145), vein_color=(0.53, 0.74, 0.22), leaf_normal_strength=0.48, leaf_roughness=0.61)
    _OLD_STYLE.update(leaf_synthesis.STYLE["DELICATE_LANCE"])
    leaf_synthesis.STYLE["DELICATE_LANCE"].update(vein=1.14, micro=0.075, mottle=0.18, curl=0.075, edge_roll=0.055, translucency=0.88, wax=0.07)
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    leaf_synthesis._render_leaf = _PREVIOUS["render_leaf"]
    leaf_synthesis._normal_from_height = _PREVIOUS["normal"]
    leaf_synthesis._write_image = _PREVIOUS["write"]
    profile = pbr_profiles.SPECIES_PBR.get("WILLOW")
    if profile:
        profile.update(_OLD_PROFILE)
    leaf_synthesis.STYLE["DELICATE_LANCE"].clear()
    leaf_synthesis.STYLE["DELICATE_LANCE"].update(_OLD_STYLE)
    _INSTALLED = False
