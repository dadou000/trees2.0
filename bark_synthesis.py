"""High-quality, species-aware procedural bark PBR synthesis.

This module replaces the original sinusoidal bark rasterizer with a deliberately
heavier texture synthesizer.  It stays fully tileable and generates a coherent
PBR set from one shared height/structure solution:

* multi-octave periodic value noise
* anisotropic ridges and fibres
* periodic Worley-style plates and fissures
* species-specific lenticels / exfoliation / papery / cork / fibrous patterns
* multi-scale cavity AO
* normals derived from the final height field
* roughness derived from cavities, exposed ridges and microstructure

The implementation uses NumPy when available (Blender ships it in normal builds).
If NumPy is unavailable Trees 2.0 falls back to the previous bark generator.
"""

import math
from array import array

try:
    import numpy as np
except Exception:  # pragma: no cover - Blender normally ships NumPy
    np = None


_PREVIOUS_GENERATE_BARK = None
_INSTALLED = False


STYLE_BY_SPECIES = {
    "GENERIC": "FURROWED",
    "OAK": "FURROWED",
    "HOLM_OAK": "FURROWED",
    "CORK_OAK": "CORK",
    "BIRCH": "PAPERY",
    "BEECH": "SMOOTH",
    "MAPLE": "FURROWED_MEDIUM",
    "ASH": "DIAMOND_FURROW",
    "ELM": "FURROWED",
    "LINDEN": "FURROWED_MEDIUM",
    "CHESTNUT": "FURROWED",
    "WALNUT": "FURROWED_MEDIUM",
    "PLANE": "EXFOLIATING",
    "ALDER": "SMOOTH_FISSURED",
    "ASPEN": "PAPERY_LIGHT",
    "POPLAR": "FURROWED_LIGHT",
    "WILLOW": "WILLOW_FURROW",
    "CHERRY": "HORIZONTAL_LENTICEL",
    "APPLE": "FURROWED_MEDIUM",
    "MAGNOLIA": "SMOOTH",
    "JACARANDA": "SMOOTH_FISSURED",
    "EUCALYPTUS": "EXFOLIATING",
    "OLIVE": "GNARLED_FURROW",
    "ACACIA": "FURROWED",
    "BAOBAB": "BROAD_FOLDS",
    "PINE": "CONIFER_PLATES",
    "STONE_PINE": "CONIFER_PLATES",
    "SPRUCE": "CONIFER_PLATES",
    "FIR": "CONIFER_PLATES_FINE",
    "CEDAR": "FIBROUS",
    "CYPRESS": "FIBROUS_FINE",
    "REDWOOD": "REDWOOD_FIBROUS",
    "DEAD_TREE": "WEATHERED",
    "WINDSWEPT": "WEATHERED",
    "SAPLING": "SMOOTH",
}


QUALITY = {
    # Working resolution is capped because structural fields do not need to be
    # evaluated at every final texel. The final PBR maps are still emitted at the
    # user-selected output resolution.
    "HIGH": (768, 4),
    "ULTRA": (1280, 5),
    "EXTREME": (2048, 6),
}


def _clamp01(a):
    return np.clip(a, 0.0, 1.0)


def _smooth01(t):
    t = _clamp01(t)
    return t * t * (3.0 - 2.0 * t)


def _smoothstep(lo, hi, x):
    if abs(hi - lo) < 1e-12:
        return (x >= hi).astype(np.float32)
    return _smooth01((x - lo) / (hi - lo))


def _normalize(a, lo_percentile=1.0, hi_percentile=99.0):
    lo = float(np.percentile(a, lo_percentile))
    hi = float(np.percentile(a, hi_percentile))
    if hi - lo < 1e-8:
        return np.zeros_like(a, dtype=np.float32)
    return _clamp01((a - lo) / (hi - lo)).astype(np.float32)


def _value_noise(size, cells_x, cells_y, rng):
    """Seamless periodic value noise evaluated with smooth bilinear interpolation."""
    cells_x = max(1, int(cells_x))
    cells_y = max(1, int(cells_y))
    grid = rng.random((cells_y, cells_x)).astype(np.float32)

    x = np.arange(size, dtype=np.float32) * (cells_x / float(size))
    y = np.arange(size, dtype=np.float32) * (cells_y / float(size))
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    tx = _smooth01(x - x0)[None, :]
    ty = _smooth01(y - y0)[:, None]
    x1 = (x0 + 1) % cells_x
    y1 = (y0 + 1) % cells_y
    x0 %= cells_x
    y0 %= cells_y

    a = grid[y0[:, None], x0[None, :]]
    b = grid[y0[:, None], x1[None, :]]
    c = grid[y1[:, None], x0[None, :]]
    d = grid[y1[:, None], x1[None, :]]
    ab = a + (b - a) * tx
    cd = c + (d - c) * tx
    return (ab + (cd - ab) * ty).astype(np.float32)


def _fbm(size, cells_x, cells_y, octaves, rng, persistence=0.52, lacunarity=2.0):
    out = np.zeros((size, size), dtype=np.float32)
    amp = 1.0
    norm = 0.0
    fx = float(cells_x)
    fy = float(cells_y)
    for _ in range(max(1, int(octaves))):
        out += _value_noise(size, max(1, round(fx)), max(1, round(fy)), rng) * amp
        norm += amp
        amp *= float(persistence)
        fx *= float(lacunarity)
        fy *= float(lacunarity)
    return (out / max(norm, 1e-8)).astype(np.float32)


def _worley(size, cells_x, cells_y, rng, stretch_x=1.0, stretch_y=1.0):
    """Periodic cellular field returning plate tone and boundary proximity."""
    cx = max(2, int(cells_x))
    cy = max(2, int(cells_y))
    off_x = (0.15 + 0.70 * rng.random((cy, cx))).astype(np.float32)
    off_y = (0.15 + 0.70 * rng.random((cy, cx))).astype(np.float32)
    values = rng.random((cy, cx)).astype(np.float32)

    gx = np.arange(size, dtype=np.float32) * (cx / float(size))
    gy = np.arange(size, dtype=np.float32) * (cy / float(size))
    ix = np.floor(gx).astype(np.int32)
    iy = np.floor(gy).astype(np.int32)
    fx = (gx - ix)[None, :]
    fy = (gy - iy)[:, None]

    d1 = np.full((size, size), 1.0e9, dtype=np.float32)
    d2 = np.full((size, size), 1.0e9, dtype=np.float32)
    nearest_value = np.zeros((size, size), dtype=np.float32)

    for oy in (-1, 0, 1):
        yy = (iy + oy) % cy
        for ox in (-1, 0, 1):
            xx = (ix + ox) % cx
            px = ox + off_x[yy[:, None], xx[None, :]]
            py = oy + off_y[yy[:, None], xx[None, :]]
            dx = (px - fx) * float(stretch_x)
            dy = (py - fy) * float(stretch_y)
            dist = dx * dx + dy * dy
            val = values[yy[:, None], xx[None, :]]

            closer = dist < d1
            d2 = np.where(closer, d1, np.minimum(d2, dist))
            nearest_value = np.where(closer, val, nearest_value)
            d1 = np.where(closer, dist, d1)

    gap = np.sqrt(np.maximum(d2, 0.0)) - np.sqrt(np.maximum(d1, 0.0))
    edge = 1.0 - _smoothstep(0.035, 0.22, gap)
    return nearest_value.astype(np.float32), edge.astype(np.float32)


def _periodic_resample(field, resolution):
    h, w = field.shape
    if h == resolution and w == resolution:
        return field.astype(np.float32, copy=False)

    x = np.arange(resolution, dtype=np.float32) * (w / float(resolution))
    y = np.arange(resolution, dtype=np.float32) * (h / float(resolution))
    x0 = np.floor(x).astype(np.int32) % w
    y0 = np.floor(y).astype(np.int32) % h
    x1 = (x0 + 1) % w
    y1 = (y0 + 1) % h
    tx = (x - np.floor(x))[None, :]
    ty = (y - np.floor(y))[:, None]

    a = field[y0[:, None], x0[None, :]]
    b = field[y0[:, None], x1[None, :]]
    c = field[y1[:, None], x0[None, :]]
    d = field[y1[:, None], x1[None, :]]
    return (a + (b - a) * tx + ((c + (d - c) * tx) - (a + (b - a) * tx)) * ty).astype(np.float32)


def _vertical_cracks(size, count, warp, breakup, depth_width=0.070):
    x = np.arange(size, dtype=np.float32)[None, :] / float(size)
    y = np.arange(size, dtype=np.float32)[:, None] / float(size)
    phase = x * max(2.0, float(count)) + (warp - 0.5) * 0.90 + 0.16 * np.sin(
        math.tau * (y * 1.7 + (warp - 0.5) * 0.35)
    )
    distance = np.abs(np.sin(math.pi * phase))
    line = np.exp(-((distance / max(depth_width, 1e-4)) ** 2)).astype(np.float32)
    continuity = 0.28 + 0.72 * _smoothstep(0.24, 0.78, breakup)
    return _clamp01(line * continuity).astype(np.float32)


def _horizontal_lenticels(size, count, warp, breakup, width=0.055):
    x = np.arange(size, dtype=np.float32)[None, :] / float(size)
    y = np.arange(size, dtype=np.float32)[:, None] / float(size)
    phase = y * max(2.0, float(count)) + (warp - 0.5) * 0.55
    distance = np.abs(np.sin(math.pi * phase))
    lines = np.exp(-((distance / max(width, 1e-4)) ** 2)).astype(np.float32)
    # Break horizontal bands into lenticel-like dashes.
    dash = _smoothstep(0.54, 0.80, breakup)
    modulation = 0.55 + 0.45 * np.sin(math.tau * (x * (count * 0.37 + 2.0) + warp * 0.8)) ** 2
    return _clamp01(lines * dash * modulation).astype(np.float32)


def _style_for_species(species):
    return STYLE_BY_SPECIES.get(str(species), "FURROWED")


def _build_structure(profile, pbr, seed, species, work_size, octaves):
    rng = np.random.default_rng(int(seed) ^ 0x4B41524B)  # 'BARK'
    detail = float(pbr.bark_detail)
    ridge_count = max(2, int(profile.get("ridge_count", 8)))
    crack_count = max(2, int(profile.get("crack_count", 13)))
    plate_scale = max(2, int(profile.get("plate_scale", 4)))
    ridge_depth = float(profile.get("ridge_depth", 0.24)) * detail
    crack_depth = float(profile.get("crack_depth", 0.32)) * detail
    fine_strength = float(profile.get("fine_strength", 0.08)) * detail
    style = _style_for_species(species)

    macro = _fbm(work_size, 2, 2, max(3, octaves - 2), rng, 0.56)
    warp = _fbm(work_size, 3, 2, max(3, octaves - 2), rng, 0.55)
    fine = _fbm(work_size, 18, 13, max(3, octaves - 2), rng, 0.48)
    micro = _fbm(work_size, 42, 31, max(2, octaves - 3), rng, 0.46)
    fiber = _fbm(work_size, max(8, ridge_count * 2), max(2, ridge_count // 3), max(3, octaves - 2), rng, 0.50)
    vertical = _vertical_cracks(work_size, crack_count, warp, fine)

    # Cell aspect changes the shape of bark plates. Fewer cells vertically gives
    # tall plates / fissures; nearly square cells give cork or scaly bark.
    if style in {"FURROWED", "WILLOW_FURROW", "GNARLED_FURROW", "FURROWED_MEDIUM", "FURROWED_LIGHT", "DIAMOND_FURROW"}:
        plate, edge = _worley(work_size, max(5, plate_scale * 2), max(2, plate_scale), rng, 1.0, 0.72)
    elif style in {"FIBROUS", "FIBROUS_FINE", "REDWOOD_FIBROUS"}:
        plate, edge = _worley(work_size, max(7, plate_scale * 2), max(2, plate_scale // 2 + 1), rng, 1.0, 0.55)
    else:
        plate, edge = _worley(work_size, max(4, plate_scale), max(4, plate_scale), rng, 1.0, 1.0)

    ridge = 1.0 - np.abs(fiber * 2.0 - 1.0)
    ridge = _normalize(ridge, 1.0, 99.0)
    lenticels = _horizontal_lenticels(work_size, max(5, crack_count), warp, fine)

    h = np.full((work_size, work_size), 0.50, dtype=np.float32)
    color_patch = (plate - 0.5).astype(np.float32)
    crack = np.zeros_like(h)
    surface = (micro - 0.5).astype(np.float32)

    if style == "CORK":
        h += (plate - 0.5) * (0.24 + ridge_depth * 0.24)
        h += (macro - 0.5) * 0.13
        h += (fine - 0.5) * 0.09
        crack = _clamp01(edge * 0.88 + vertical * 0.25)
        h -= crack * (0.28 + crack_depth * 0.45)
        pores = _smoothstep(0.73, 0.91, micro) * (0.35 + 0.65 * _smoothstep(0.45, 0.85, fine))
        h -= pores * 0.075
        surface += pores * 0.20
    elif style in {"PAPERY", "PAPERY_LIGHT"}:
        h += (macro - 0.5) * 0.055
        h += (fine - 0.5) * 0.028
        peel = _horizontal_lenticels(work_size, max(3, plate_scale // 2 + 2), macro, warp, 0.10)
        h += peel * 0.030
        crack = _clamp01(lenticels * (0.62 if style == "PAPERY" else 0.44) + edge * 0.16)
        h -= crack * (0.045 + crack_depth * 0.10)
        color_patch = (macro - 0.5) * 0.55 + (plate - 0.5) * 0.25
        surface += lenticels * 0.08
    elif style in {"SMOOTH", "SMOOTH_FISSURED"}:
        h += (macro - 0.5) * (0.055 if style == "SMOOTH" else 0.080)
        h += (fine - 0.5) * 0.030
        crack = lenticels * (0.22 if style == "SMOOTH" else 0.38)
        if style == "SMOOTH_FISSURED":
            crack = _clamp01(crack + vertical * 0.22 + edge * 0.12)
        h -= crack * (0.028 + crack_depth * 0.08)
        color_patch = (macro - 0.5) * 0.42
    elif style == "HORIZONTAL_LENTICEL":
        h += (macro - 0.5) * 0.055 + (fine - 0.5) * 0.030
        crack = _clamp01(lenticels * 0.82 + edge * 0.08)
        h -= crack * (0.035 + crack_depth * 0.05)
        color_patch = (macro - 0.5) * 0.35
        surface += lenticels * 0.14
    elif style == "EXFOLIATING":
        h += (plate - 0.5) * 0.085
        h += (macro - 0.5) * 0.055
        h += (fine - 0.5) * 0.025
        crack = _clamp01(edge * 0.48 + vertical * 0.10)
        h -= crack * (0.050 + crack_depth * 0.12)
        # Plate values drive the distinctive patchwork color more than relief.
        color_patch = (plate - 0.5) * 1.55 + (macro - 0.5) * 0.35
        surface += edge * 0.10
    elif style in {"CONIFER_PLATES", "CONIFER_PLATES_FINE"}:
        plate_weight = 0.19 if style == "CONIFER_PLATES" else 0.12
        h += (plate - 0.5) * plate_weight
        h += (ridge - 0.5) * ridge_depth * (0.30 if style == "CONIFER_PLATES" else 0.18)
        h += (fine - 0.5) * 0.055
        crack = _clamp01(edge * 0.72 + vertical * 0.42)
        h -= crack * (0.14 + crack_depth * 0.28)
        color_patch = (plate - 0.5) * 0.82 + (macro - 0.5) * 0.28
    elif style in {"FIBROUS", "FIBROUS_FINE", "REDWOOD_FIBROUS"}:
        strength = 1.0 if style != "FIBROUS_FINE" else 0.68
        if style == "REDWOOD_FIBROUS":
            strength = 1.22
        h += (ridge - 0.5) * ridge_depth * 0.95 * strength
        h += (macro - 0.5) * 0.11
        h += (fine - 0.5) * 0.075
        crack = _clamp01(vertical * (0.72 + 0.16 * strength) + edge * 0.28)
        h -= crack * (0.12 + crack_depth * 0.24)
        color_patch = (fiber - 0.5) * 0.70 + (macro - 0.5) * 0.30
        surface += (ridge - 0.5) * 0.28
    elif style == "BROAD_FOLDS":
        broad = _fbm(work_size, 5, 2, max(3, octaves - 2), rng, 0.58)
        fold = 1.0 - np.abs(broad * 2.0 - 1.0)
        h += (fold - 0.5) * 0.15
        h += (macro - 0.5) * 0.06
        h += (fine - 0.5) * 0.025
        crack = _clamp01(vertical * 0.16 + lenticels * 0.08)
        h -= crack * 0.025
        color_patch = (macro - 0.5) * 0.38
    elif style == "WEATHERED":
        h += (plate - 0.5) * 0.12
        h += (ridge - 0.5) * ridge_depth * 0.45
        h += (fine - 0.5) * 0.085
        crack = _clamp01(edge * 0.62 + vertical * 0.62)
        h -= crack * (0.15 + crack_depth * 0.30)
        color_patch = (plate - 0.5) * 0.62 + (macro - 0.5) * 0.45
        surface += micro * 0.10
    else:
        # Furrowed families, including willow/olive/ash variants.
        ridge_gain = {
            "FURROWED_LIGHT": 0.46,
            "FURROWED_MEDIUM": 0.68,
            "DIAMOND_FURROW": 0.78,
            "WILLOW_FURROW": 0.82,
            "GNARLED_FURROW": 1.08,
        }.get(style, 0.92)
        h += (ridge - 0.5) * ridge_depth * ridge_gain
        h += (macro - 0.5) * (0.08 if style != "GNARLED_FURROW" else 0.14)
        h += (fine - 0.5) * (0.050 + fine_strength * 0.35)
        crack = _clamp01(vertical * 0.70 + edge * (0.36 if style != "DIAMOND_FURROW" else 0.58))
        if style == "DIAMOND_FURROW":
            diagonal = np.roll(vertical, work_size // max(8, crack_count), axis=0)
            crack = _clamp01(crack + diagonal * 0.28)
        h -= crack * (0.10 + crack_depth * 0.25)
        color_patch = (ridge - 0.5) * 0.42 + (plate - 0.5) * 0.22
        if style == "GNARLED_FURROW":
            h += (plate - 0.5) * 0.08
            surface += edge * 0.14

    h += surface * (0.020 + fine_strength * 0.16)
    h = _normalize(h, 0.5, 99.5)
    return {
        "height": h,
        "crack": _clamp01(crack).astype(np.float32),
        "macro": macro.astype(np.float32),
        "fine": fine.astype(np.float32),
        "micro": micro.astype(np.float32),
        "plate": plate.astype(np.float32),
        "edge": edge.astype(np.float32),
        "lenticel": lenticels.astype(np.float32),
        "color_patch": color_patch.astype(np.float32),
        "style": style,
    }


def _derive_ao(height, crack, strength):
    cavity = np.zeros_like(height, dtype=np.float32)
    weight_sum = 0.0
    for radius, weight in ((1, 0.28), (2, 0.24), (4, 0.20), (8, 0.16), (16, 0.12)):
        neighbors = (
            np.roll(height, radius, axis=0)
            + np.roll(height, -radius, axis=0)
            + np.roll(height, radius, axis=1)
            + np.roll(height, -radius, axis=1)
        ) * 0.25
        cavity += np.maximum(0.0, neighbors - height) * weight
        weight_sum += weight
    cavity /= max(weight_sum, 1e-8)
    ao = 1.0 - cavity * (2.4 + float(strength) * 4.2) - crack * float(strength) * 0.16
    return np.clip(ao, 0.28, 1.0).astype(np.float32)


def _derive_normal(height, pbr_strength, profile_strength):
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    # Legacy profiles used values around 4-5. Normalize those into a sensible
    # texture-space gradient scale; the material applies its own conservative
    # Normal Map node strength afterwards.
    profile_factor = max(0.45, min(1.55, float(profile_strength) / 4.2))
    strength = 13.0 * float(pbr_strength) * profile_factor
    nx = -dx * strength
    ny = -dy * strength
    nz = np.ones_like(height, dtype=np.float32)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    return (
        nx * inv * 0.5 + 0.5,
        ny * inv * 0.5 + 0.5,
        nz * inv * 0.5 + 0.5,
    )


def _colorize(profile, fields, ao):
    h = fields["height"]
    crack = fields["crack"]
    macro = fields["macro"]
    fine = fields["fine"]
    plate = fields["plate"]
    lenticel = fields["lenticel"]
    patch = fields["color_patch"]
    style = fields["style"]

    base = np.asarray(profile.get("bark_base", (0.24, 0.14, 0.07)), dtype=np.float32)
    light = np.asarray(profile.get("bark_light", (0.40, 0.26, 0.14)), dtype=np.float32)
    dark = np.asarray(profile.get("bark_dark", (0.08, 0.045, 0.025)), dtype=np.float32)

    tone = _clamp01(0.48 + (h - 0.5) * 0.58 + patch * 0.18 + (macro - 0.5) * 0.10)
    if style in {"PAPERY", "PAPERY_LIGHT"}:
        tone = _clamp01(0.70 + (macro - 0.5) * 0.18 + patch * 0.10)
    elif style == "EXFOLIATING":
        tone = _clamp01(0.50 + (plate - 0.5) * 0.72 + (macro - 0.5) * 0.16)
    elif style == "HORIZONTAL_LENTICEL":
        tone = _clamp01(0.54 + (h - 0.5) * 0.36 + (macro - 0.5) * 0.20)
    elif style == "WEATHERED":
        tone = _clamp01(0.62 + patch * 0.26 + (fine - 0.5) * 0.12)

    rgb = np.empty((h.shape[0], h.shape[1], 3), dtype=np.float32)
    for channel in range(3):
        rgb[..., channel] = dark[channel] + (light[channel] - dark[channel]) * tone
        rgb[..., channel] = rgb[..., channel] * 0.78 + base[channel] * 0.22

    # Fissures are dark because they are recessed and collect soil/moisture.
    rgb *= (1.0 - crack[..., None] * 0.46)

    if style in {"PAPERY", "PAPERY_LIGHT"}:
        # Birch/aspen bark has dark scars and lenticels over a light body.
        rgb = rgb * (1.0 - lenticel[..., None] * (0.50 if style == "PAPERY" else 0.34))
    elif style == "HORIZONTAL_LENTICEL":
        # Cherry lenticels tend to read as lighter horizontal marks.
        rgb += lenticel[..., None] * (light[None, None, :] - rgb) * 0.48
    elif style == "EXFOLIATING":
        warm = np.asarray((0.58, 0.43, 0.26), dtype=np.float32)
        cool = np.asarray((0.31, 0.35, 0.28), dtype=np.float32)
        mask = _smoothstep(0.60, 0.84, plate)[..., None]
        rgb = rgb * (1.0 - mask * 0.18) + warm[None, None, :] * mask * 0.18
        mask2 = _smoothstep(0.08, 0.28, plate)[..., None]
        rgb = rgb * (1.0 - mask2 * 0.12) + cool[None, None, :] * mask2 * 0.12
    elif style == "WEATHERED":
        gray = rgb.mean(axis=2, keepdims=True)
        rgb = rgb * 0.68 + gray * 0.32
        bleach = _smoothstep(0.66, 0.90, fields["micro"])[..., None]
        rgb = rgb * (1.0 - bleach * 0.18) + 0.62 * bleach * 0.18

    moss = float(profile.get("moss", 0.0))
    if moss > 0.0:
        moss_mask = _smoothstep(0.62, 0.88, fields["fine"]) * _smoothstep(0.0, 0.35, 1.0 - ao)
        moss_color = np.asarray((0.17, 0.24, 0.08), dtype=np.float32)
        rgb = rgb * (1.0 - moss_mask[..., None] * moss) + moss_color * (moss_mask[..., None] * moss)

    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def _rgba_array_from_rgb(rgb):
    h, w, _ = rgb.shape
    out = np.empty((h, w, 4), dtype=np.float32)
    out[..., :3] = rgb
    out[..., 3] = 1.0
    return array("f", out.reshape(-1))


def _rgba_array_from_gray(gray):
    h, w = gray.shape
    out = np.empty((h, w, 4), dtype=np.float32)
    out[..., 0] = gray
    out[..., 1] = gray
    out[..., 2] = gray
    out[..., 3] = 1.0
    return array("f", out.reshape(-1))


def _rgba_array_from_normal(normal_tuple):
    nx, ny, nz = normal_tuple
    h, w = nx.shape
    out = np.empty((h, w, 4), dtype=np.float32)
    out[..., 0] = nx
    out[..., 1] = ny
    out[..., 2] = nz
    out[..., 3] = 1.0
    return array("f", out.reshape(-1))


def _generate_bark_hq(profile, pbr, seed, species, output):
    if np is None:
        return _PREVIOUS_GENERATE_BARK(profile, pbr, seed, species, output)

    from . import procedural_pbr

    resolution = int(pbr.bark_resolution)
    quality_name = str(getattr(pbr, "bark_quality", "ULTRA"))
    work_cap, octaves = QUALITY.get(quality_name, QUALITY["ULTRA"])
    work_size = min(resolution, work_cap)

    fields = _build_structure(profile, pbr, seed, species, work_size, octaves)
    if work_size != resolution:
        for key in ("height", "crack", "macro", "fine", "micro", "plate", "edge", "lenticel", "color_patch"):
            fields[key] = _periodic_resample(fields[key], resolution)

    height = _clamp01(fields["height"])
    ao = _derive_ao(height, fields["crack"], profile.get("ao_strength", 0.46))
    normals = _derive_normal(
        height,
        pbr.bark_normal_strength,
        profile.get("bark_normal_strength", 4.2),
    )
    rgb = _colorize(profile, fields, ao)

    base_roughness = float(profile.get("bark_roughness", 0.82))
    cavity = 1.0 - ao
    ridge_exposure = _smoothstep(0.62, 0.88, height)
    roughness = (
        base_roughness
        + fields["crack"] * 0.055
        + cavity * 0.080
        + (fields["micro"] - 0.5) * 0.075
        - ridge_exposure * 0.030
    )
    roughness = np.clip(roughness, 0.55, 0.99).astype(np.float32)

    stem = f"trees2_{procedural_pbr._safe_name(species)}_{seed}_bark"
    result = {
        "albedo": procedural_pbr._new_image(
            f"{stem}_albedo", resolution, resolution, _rgba_array_from_rgb(rgb),
            output / f"{stem}_albedo.png", False, pbr.pack_images,
        ),
        "normal": procedural_pbr._new_image(
            f"{stem}_normal", resolution, resolution, _rgba_array_from_normal(normals),
            output / f"{stem}_normal.png", True, pbr.pack_images,
        ),
        "roughness": procedural_pbr._new_image(
            f"{stem}_roughness", resolution, resolution, _rgba_array_from_gray(roughness),
            output / f"{stem}_roughness.png", True, pbr.pack_images,
        ),
        "height": procedural_pbr._new_image(
            f"{stem}_height", resolution, resolution, _rgba_array_from_gray(height),
            output / f"{stem}_height.png", True, pbr.pack_images,
        ),
        "ao": procedural_pbr._new_image(
            f"{stem}_ao", resolution, resolution, _rgba_array_from_gray(ao),
            output / f"{stem}_ao.png", True, pbr.pack_images,
        ),
    }

    style = _style_for_species(species)
    for image in result.values():
        image["trees2_bark_generator"] = "HQ_BARK_V2"
        image["trees2_bark_style"] = style
        image["trees2_bark_quality"] = quality_name
        image["trees2_bark_seed"] = int(seed)
    return result


def install():
    global _PREVIOUS_GENERATE_BARK, _INSTALLED
    if _INSTALLED:
        return
    from . import procedural_pbr

    _PREVIOUS_GENERATE_BARK = procedural_pbr._generate_bark
    procedural_pbr._generate_bark = _generate_bark_hq
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    from . import procedural_pbr

    procedural_pbr._generate_bark = _PREVIOUS_GENERATE_BARK
    _INSTALLED = False
