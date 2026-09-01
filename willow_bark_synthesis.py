"""Photorealistic-leaning weeping-willow bark PBR synthesis.

The previous willow solve improved on the generic sine-like furrows, but its
macro skeleton still consisted of continuous strips running from one side of
the tile to the other. Mature Salix bark is better represented as a hierarchy
of elongated, fractured plates: major riven boundaries split and merge, plate
shoulders lift irregularly, secondary cracks subdivide old bark, and the plate
surface carries strongly anisotropic fibres and dry micro-breakup.

This module intercepts bark generation only for WILLOW. Every other species
falls through to the normal Trees 2.0 high-quality bark generator.

Important implementation details:
* no sine-wave furrow primitive
* native-resolution structural solve up to the requested output resolution
* elongated periodic cellular plates instead of uninterrupted stripes
* boundary-orientation weighting keeps the network predominantly longitudinal
  without making every crack vertical
* two fracture scales plus sparse longitudinal tears
* lifted/torn plate shoulders and independent plate height offsets
* resolution-independent tangent-space normal derivation
* multi-scale cavity AO whose physical support scales with output resolution
* deterministic roughness and albedo from the same structural solution
* defensive NaN/range sanitation and map statistics stored on generated images
"""

from array import array
import math

try:
    import numpy as np
except Exception:  # pragma: no cover - normal Blender builds ship NumPy
    np = None

from . import bark_synthesis


_PREVIOUS_GENERATE_BARK = None
_INSTALLED = False


QUALITY = {
    "HIGH": dict(
        macro_x=10, macro_y=3,
        secondary_x=24, secondary_y=8,
        fbm_octaves=4, fibre_octaves=3,
        micro_x=150, micro_y=42,
    ),
    "ULTRA": dict(
        macro_x=12, macro_y=3,
        secondary_x=30, secondary_y=9,
        fbm_octaves=5, fibre_octaves=4,
        micro_x=210, micro_y=58,
    ),
    "EXTREME": dict(
        macro_x=14, macro_y=4,
        secondary_x=38, secondary_y=11,
        fbm_octaves=6, fibre_octaves=5,
        micro_x=290, micro_y=78,
    ),
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


def _sanitize(field, fill=0.0):
    return np.nan_to_num(field, nan=float(fill), posinf=1.0, neginf=0.0).astype(np.float32)


def _normalize(field, lo=0.15, hi=99.85):
    field = _sanitize(field)
    low = float(np.percentile(field, lo))
    high = float(np.percentile(field, hi))
    if high - low <= 1.0e-8:
        return np.zeros_like(field, dtype=np.float32)
    return np.clip((field - low) / (high - low), 0.0, 1.0).astype(np.float32)


def _local_contrast(field, amount=0.52):
    """Periodic edge-preserving unsharp pass.

    This is intentionally tiny-radius. It restores crisp crack shoulders after
    the structural composition without turning broad bark forms into halos.
    """
    low = (
        np.roll(field, 1, axis=0)
        + np.roll(field, -1, axis=0)
        + np.roll(field, 1, axis=1)
        + np.roll(field, -1, axis=1)
    ) * 0.25
    return np.clip(field + (field - low) * float(amount), 0.0, 1.0).astype(np.float32)


def _highpass(field, radius=1):
    low = (
        np.roll(field, radius, axis=0)
        + np.roll(field, -radius, axis=0)
        + np.roll(field, radius, axis=1)
        + np.roll(field, -radius, axis=1)
    ) * 0.25
    return (field - low).astype(np.float32)


def _periodic_worley_gap(size, cells_x, cells_y, rng):
    """Periodic cellular field returning cell value, F2-F1 gap and nearest distance.

    The public HQ bark helper only exposes a pre-shaped edge mask. For willow we
    retain the F2-F1 distance because it lets us derive crack orientation and
    build sharp plate shoulders without a second blur-like reconstruction.
    """
    cx = max(2, int(cells_x))
    cy = max(2, int(cells_y))
    off_x = (0.10 + 0.80 * rng.random((cy, cx))).astype(np.float32)
    off_y = (0.10 + 0.80 * rng.random((cy, cx))).astype(np.float32)
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
            dx = px - fx
            dy = py - fy
            distance = dx * dx + dy * dy
            value = values[yy[:, None], xx[None, :]]

            closer = distance < d1
            d2 = np.where(closer, d1, np.minimum(d2, distance))
            nearest_value = np.where(closer, value, nearest_value)
            d1 = np.where(closer, distance, d1)

    gap = np.sqrt(np.maximum(d2, 0.0)) - np.sqrt(np.maximum(d1, 0.0))
    return (
        nearest_value.astype(np.float32),
        gap.astype(np.float32),
        np.sqrt(np.maximum(d1, 0.0)).astype(np.float32),
    )


def _boundary_verticality(gap):
    """0 for mainly horizontal boundaries, 1 for mainly vertical boundaries."""
    dx = (np.roll(gap, -1, axis=1) - np.roll(gap, 1, axis=1)) * 0.5
    dy = (np.roll(gap, -1, axis=0) - np.roll(gap, 1, axis=0)) * 0.5
    ax = np.abs(dx)
    ay = np.abs(dy)
    return (ax / np.maximum(ax + ay, 1.0e-7)).astype(np.float32)


def _edge_from_gap(gap, narrow, wide):
    return (1.0 - _smoothstep(float(narrow), float(wide), gap)).astype(np.float32)


def _ridged(field):
    return (1.0 - np.abs(field * 2.0 - 1.0)).astype(np.float32)


def _build_structure(profile, pbr, seed, resolution, quality_name):
    rng = np.random.default_rng(int(seed) ^ 0x57564234)  # 'WVB4'
    q = QUALITY.get(quality_name, QUALITY["ULTRA"])
    detail = max(0.25, float(pbr.bark_detail))

    # Macro elongated plates. The small Y-cell count makes the cells tall in UV
    # space. Boundary orientation then suppresses most wall-like horizontal
    # edges while retaining enough diagonal connectors for real split/merge
    # topology.
    macro_value, macro_gap, _macro_d1 = _periodic_worley_gap(
        resolution, q["macro_x"], q["macro_y"], rng
    )
    macro_verticality = _boundary_verticality(macro_gap)
    macro_edge_raw = _edge_from_gap(macro_gap, 0.012, 0.105)

    macro_gate = bark_synthesis._fbm(
        resolution, 6, 4, max(3, q["fbm_octaves"] - 1), rng, 0.56
    )
    macro_gate = 0.48 + 0.52 * _smoothstep(0.20, 0.80, macro_gate)
    macro_crack = macro_edge_raw * (0.15 + 0.85 * np.power(macro_verticality, 0.58))
    macro_crack *= macro_gate
    macro_crack = _clamp01(macro_crack)

    # Interior is deliberately derived from boundary distance, not from a broad
    # sinusoidal ridge. It therefore forms plate masses with locally flat-ish
    # centres and sharp shoulders.
    macro_interior = _smoothstep(0.020, 0.185, macro_gap)

    # Secondary cells fracture the old bark within the major plates. These are
    # smaller and less strongly direction-filtered, allowing diagonal tears and
    # short cross-cracks without turning the surface into stone polygons.
    secondary_value, secondary_gap, _secondary_d1 = _periodic_worley_gap(
        resolution, q["secondary_x"], q["secondary_y"], rng
    )
    secondary_verticality = _boundary_verticality(secondary_gap)
    secondary_edge = _edge_from_gap(secondary_gap, 0.010, 0.082)
    secondary_edge *= 0.24 + 0.76 * np.power(secondary_verticality, 0.72)
    secondary_edge *= _smoothstep(0.18, 0.82, macro_interior)

    chunk = bark_synthesis._fbm(
        resolution, max(7, q["macro_x"]), 6,
        q["fbm_octaves"], rng, 0.52,
    )
    macro_noise = bark_synthesis._fbm(
        resolution, 3, 2, max(3, q["fbm_octaves"] - 1), rng, 0.58,
    )

    # Crack widths and survival are modulated independently. This avoids the
    # procedural tell of identical dark lines and gives some fissures pinched,
    # widened or locally interrupted portions.
    crack_breakup = bark_synthesis._fbm(
        resolution, max(22, q["secondary_x"]), 13,
        max(3, q["fbm_octaves"] - 1), rng, 0.48,
    )
    secondary_crack = secondary_edge * (0.36 + 0.64 * _smoothstep(0.25, 0.78, crack_breakup))

    # Longitudinal bark fibres and sparse internal tears. High X / low Y cell
    # counts make the field strongly anisotropic in image space.
    fibre_coarse = bark_synthesis._fbm(
        resolution, 72, 9, q["fibre_octaves"], rng, 0.48,
    )
    fibre_fine = bark_synthesis._fbm(
        resolution, 168, 24, max(3, q["fibre_octaves"] - 1), rng, 0.45,
    )
    fibre_ridge = _ridged(fibre_coarse)
    sparse_tear = _smoothstep(0.84, 0.965, fibre_ridge)
    sparse_tear *= _smoothstep(0.24, 0.86, macro_interior)
    sparse_tear *= 0.45 + 0.55 * _smoothstep(0.30, 0.76, chunk)

    micro = bark_synthesis._fbm(
        resolution,
        q["micro_x"], q["micro_y"],
        max(3, q["fibre_octaves"] - 1), rng, 0.43,
    )
    micro_high = _highpass(micro, 1)

    # Tiny dry pits and pin fractures. Keep them sparse so they read as bark
    # surface breakup rather than procedural speckle.
    pore_noise = bark_synthesis._fbm(
        resolution,
        max(90, q["micro_x"] // 2), max(32, q["micro_y"] // 2),
        3, rng, 0.42,
    )
    pores = _smoothstep(0.84, 0.955, pore_noise)
    pores *= _smoothstep(0.16, 0.88, macro_interior)

    # Raised shoulders around macro fissures. A band-pass of macro_edge_raw gives
    # a lip just inside a crack instead of lifting the whole plate boundary.
    shoulder_band = _smoothstep(0.12, 0.50, macro_edge_raw) * (1.0 - _smoothstep(0.62, 0.94, macro_edge_raw))
    shoulder_gate = 0.28 + 0.72 * _smoothstep(0.30, 0.79, chunk)
    shoulder = _clamp01(shoulder_band * shoulder_gate * (0.40 + 0.60 * macro_verticality))

    # Selected secondary plate edges curl/lift slightly, producing the torn,
    # layered character visible on mature willow without baking a directional
    # light into albedo.
    flake_select = _smoothstep(0.58, 0.86, secondary_value)
    flake_lift = secondary_edge * flake_select * macro_interior
    flake_lift *= 0.32 + 0.68 * _smoothstep(0.28, 0.76, chunk)

    ridge_depth = max(0.22, float(profile.get("ridge_depth", 0.32))) * detail
    crack_depth = max(0.34, float(profile.get("crack_depth", 0.46))) * detail
    fine_strength = max(0.08, float(profile.get("fine_strength", 0.12))) * detail

    # Piecewise plate offsets are important: real bark has adjacent plates at
    # visibly different elevations. The nearest-cell values create those broad
    # offsets while the boundary masks create the actual fissures between them.
    height = np.full((resolution, resolution), 0.46, dtype=np.float32)
    height += (macro_value - 0.5) * 0.22
    height += macro_interior * (0.15 + ridge_depth * 0.20)
    height += (secondary_value - 0.5) * 0.070 * macro_interior
    height += (macro_noise - 0.5) * 0.085
    height += (chunk - 0.5) * 0.115 * macro_interior
    height += shoulder * (0.105 + ridge_depth * 0.12)
    height += flake_lift * (0.065 + ridge_depth * 0.08)

    height -= macro_crack * (0.43 + crack_depth * 0.35)
    height -= secondary_crack * (0.115 + crack_depth * 0.12)
    height -= sparse_tear * (0.060 + crack_depth * 0.075)
    height -= pores * 0.030 * detail

    # Fibres are relief, not only color noise. Two anisotropic scales plus a
    # high-passed micro field produce visible dry grain at 2K/4K.
    height += (fibre_coarse - 0.5) * (0.075 + fine_strength * 0.30) * macro_interior
    height += (fibre_fine - 0.5) * (0.040 + fine_strength * 0.20) * macro_interior
    height += micro_high * (0.115 + fine_strength * 0.32) * macro_interior

    height = _normalize(height, 0.10, 99.90)
    contrast = 0.64 if quality_name == "EXTREME" else (0.56 if quality_name == "ULTRA" else 0.48)
    height = _local_contrast(height, contrast)
    height = _sanitize(height)

    crack = _clamp01(
        np.maximum(
            macro_crack,
            np.maximum(secondary_crack * 0.78, sparse_tear * 0.62),
        )
    )

    return {
        "height": height,
        "crack": crack,
        "macro_crack": macro_crack,
        "secondary_crack": secondary_crack,
        "sparse_tear": sparse_tear,
        "macro_value": macro_value,
        "secondary_value": secondary_value,
        "macro_interior": macro_interior,
        "macro_verticality": macro_verticality,
        "shoulder": shoulder,
        "flake_lift": flake_lift,
        "chunk": chunk.astype(np.float32),
        "macro_noise": macro_noise.astype(np.float32),
        "fibre_coarse": fibre_coarse.astype(np.float32),
        "fibre_fine": fibre_fine.astype(np.float32),
        "micro": micro.astype(np.float32),
        "pores": pores.astype(np.float32),
        "style": "WILLOW_FRACTURED_PLATES_V4",
    }


def _derive_ao(height, crack, resolution, strength):
    """Multi-scale periodic cavity AO with resolution-scaled support."""
    cavity = np.zeros_like(height, dtype=np.float32)
    scale = max(1, int(round(resolution / 1024.0)))
    samples = (
        (1 * scale, 0.08),
        (2 * scale, 0.09),
        (4 * scale, 0.10),
        (8 * scale, 0.12),
        (16 * scale, 0.15),
        (32 * scale, 0.17),
        (64 * scale, 0.17),
        (96 * scale, 0.12),
    )
    for radius, weight in samples:
        radius = max(1, min(max(1, resolution // 6), int(radius)))
        neighbors = (
            np.roll(height, radius, axis=0)
            + np.roll(height, -radius, axis=0)
            + np.roll(height, radius, axis=1)
            + np.roll(height, -radius, axis=1)
        ) * 0.25
        cavity += np.maximum(0.0, neighbors - height) * float(weight)

    amount = max(0.35, float(strength))
    ao = 1.0 - cavity * (5.0 + amount * 4.2) - crack * (0.10 + amount * 0.12)
    return np.clip(_sanitize(ao, 1.0), 0.16, 1.0).astype(np.float32)


def _derive_normal_uv(height, resolution, pbr_strength, profile_strength):
    """Resolution-independent tangent-space normal from UV-space derivatives.

    The old helper measured height change per pixel using a fixed multiplier.
    Doubling texture resolution therefore halved the apparent surface slope.
    Here the finite difference is converted back to a UV derivative by
    multiplying by resolution before applying the physical relief amplitude.
    """
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5 * float(resolution)
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5 * float(resolution)

    profile_factor = max(0.72, min(1.45, float(profile_strength) / 4.2))
    amplitude = 0.0095 * max(0.0, float(pbr_strength)) * profile_factor
    nx = -dx * amplitude
    ny = -dy * amplitude
    nz = np.ones_like(height, dtype=np.float32)
    inv = 1.0 / np.sqrt(np.maximum(nx * nx + ny * ny + nz * nz, 1.0e-12))

    return (
        np.clip(nx * inv * 0.5 + 0.5, 0.0, 1.0).astype(np.float32),
        np.clip(ny * inv * 0.5 + 0.5, 0.0, 1.0).astype(np.float32),
        np.clip(nz * inv * 0.5 + 0.5, 0.0, 1.0).astype(np.float32),
    )


def _colorize(profile, fields, ao):
    height = fields["height"]
    crack = fields["crack"]
    macro_value = fields["macro_value"]
    secondary_value = fields["secondary_value"]
    chunk = fields["chunk"]
    fibre = fields["fibre_coarse"]
    shoulder = fields["shoulder"]
    flake = fields["flake_lift"]
    micro = fields["micro"]

    base = np.asarray(profile.get("bark_base", (0.31, 0.27, 0.20)), dtype=np.float32)
    light = np.asarray(profile.get("bark_light", (0.48, 0.41, 0.31)), dtype=np.float32)
    dark = np.asarray(profile.get("bark_dark", (0.080, 0.055, 0.038)), dtype=np.float32)

    # Reduce chroma slightly; mature willow often reads grey-brown. This image is
    # still treated as detail under Trees 2.0's authoritative trunk tint.
    for palette in (base, light, dark):
        gray = float(palette.mean())
        palette[:] = palette * 0.82 + gray * 0.18

    tone = _clamp01(
        0.47
        + (macro_value - 0.5) * 0.34
        + (secondary_value - 0.5) * 0.11
        + (chunk - 0.5) * 0.18
        + (fibre - 0.5) * 0.10
        + (height - 0.5) * 0.18
    )

    rgb = dark[None, None, :] + (light - dark)[None, None, :] * tone[..., None]
    rgb = rgb * 0.56 + base[None, None, :] * 0.44

    # Fissures are materially darker; this is cavity/dirt variation rather than
    # a fake directional shadow. Keep the plate bodies comparatively neutral so
    # normals/height do the geometric work in the final material.
    rgb *= 1.0 - crack[..., None] * 0.51

    dry_color = np.asarray((0.56, 0.49, 0.39), dtype=np.float32)
    dry_mask = _clamp01(shoulder * 0.72 + flake * 0.58)[..., None]
    rgb = rgb * (1.0 - dry_mask * 0.13) + dry_color[None, None, :] * dry_mask * 0.13

    # Fine dusty/weathered breakup at native resolution.
    weather = _smoothstep(0.69, 0.91, micro)[..., None]
    gray = rgb.mean(axis=2, keepdims=True)
    rgb = rgb * (1.0 - weather * 0.075) + gray * weather * 0.075

    # Small AO contribution only. Most cavity shading should happen in the
    # shader, not be permanently baked into base color.
    rgb *= 0.94 + 0.06 * ao[..., None]
    return np.clip(_sanitize(rgb), 0.0, 1.0).astype(np.float32)


def _derive_roughness(profile, fields, ao):
    base = float(profile.get("bark_roughness", 0.88))
    crack = fields["crack"]
    fibre = np.abs(fields["fibre_fine"] - 0.5) * 2.0
    micro = fields["micro"]
    cavity = 1.0 - ao
    exposed = _smoothstep(0.66, 0.92, fields["height"])
    dry_edge = _clamp01(fields["shoulder"] + fields["flake_lift"] * 0.7)

    roughness = (
        base
        + crack * 0.065
        + cavity * 0.090
        + fibre * 0.075
        + (micro - 0.5) * 0.085
        + dry_edge * 0.035
        - exposed * 0.035
    )
    return np.clip(_sanitize(roughness, base), 0.58, 0.995).astype(np.float32)


def _rgba_rgb(rgb):
    h, w, _ = rgb.shape
    out = np.empty((h, w, 4), dtype=np.float32)
    out[..., :3] = rgb
    out[..., 3] = 1.0
    return array("f", out.reshape(-1))


def _rgba_gray(gray):
    gray = _sanitize(gray)
    h, w = gray.shape
    out = np.empty((h, w, 4), dtype=np.float32)
    out[..., 0] = gray
    out[..., 1] = gray
    out[..., 2] = gray
    out[..., 3] = 1.0
    return array("f", out.reshape(-1))


def _rgba_normal(normals):
    nx, ny, nz = normals
    h, w = nx.shape
    out = np.empty((h, w, 4), dtype=np.float32)
    out[..., 0] = nx
    out[..., 1] = ny
    out[..., 2] = nz
    out[..., 3] = 1.0
    return array("f", out.reshape(-1))


def _stats(field):
    field = np.asarray(field, dtype=np.float32)
    finite = field[np.isfinite(field)]
    if finite.size == 0:
        return (0.0, 0.0, 0.0)
    return (float(finite.min()), float(finite.max()), float(finite.std()))


def _tag_map(image, generator, quality, resolution, seed, map_name, stats):
    image["trees2_bark_generator"] = generator
    image["trees2_bark_style"] = "WILLOW_FRACTURED_PLATES_V4"
    image["trees2_bark_quality"] = quality
    image["trees2_bark_native_resolution"] = int(resolution)
    image["trees2_bark_seed"] = int(seed)
    image["trees2_map_kind"] = str(map_name)
    image["trees2_map_min"] = float(stats[0])
    image["trees2_map_max"] = float(stats[1])
    image["trees2_map_std"] = float(stats[2])


def _generate_willow_bark(profile, pbr, seed, species, output):
    if np is None:
        return _PREVIOUS_GENERATE_BARK(profile, pbr, seed, species, output)

    from . import procedural_pbr

    resolution = int(pbr.bark_resolution)
    quality_name = str(getattr(pbr, "bark_quality", "ULTRA"))
    fields = _build_structure(profile, pbr, seed, resolution, quality_name)

    height = np.clip(_sanitize(fields["height"]), 0.0, 1.0)
    ao = _derive_ao(
        height,
        fields["crack"],
        resolution,
        profile.get("ao_strength", 0.56),
    )
    normals = _derive_normal_uv(
        height,
        resolution,
        pbr.bark_normal_strength,
        profile.get("bark_normal_strength", 4.8),
    )
    roughness = _derive_roughness(profile, fields, ao)
    rgb = _colorize(profile, fields, ao)

    stem = f"trees2_{procedural_pbr._safe_name(species)}_{seed}_bark"
    result = {
        "albedo": procedural_pbr._new_image(
            f"{stem}_albedo", resolution, resolution, _rgba_rgb(rgb),
            output / f"{stem}_albedo.png", False, pbr.pack_images,
        ),
        "normal": procedural_pbr._new_image(
            f"{stem}_normal", resolution, resolution, _rgba_normal(normals),
            output / f"{stem}_normal.png", True, pbr.pack_images,
        ),
        "roughness": procedural_pbr._new_image(
            f"{stem}_roughness", resolution, resolution, _rgba_gray(roughness),
            output / f"{stem}_roughness.png", True, pbr.pack_images,
        ),
        "height": procedural_pbr._new_image(
            f"{stem}_height", resolution, resolution, _rgba_gray(height),
            output / f"{stem}_height.png", True, pbr.pack_images,
        ),
        "ao": procedural_pbr._new_image(
            f"{stem}_ao", resolution, resolution, _rgba_gray(ao),
            output / f"{stem}_ao.png", True, pbr.pack_images,
        ),
    }

    normal_stack = np.stack(normals, axis=2)
    map_fields = {
        "albedo": rgb,
        "normal": normal_stack,
        "roughness": roughness,
        "height": height,
        "ao": ao,
    }
    for name, image in result.items():
        _tag_map(
            image,
            "WILLOW_FRACTURED_V4",
            quality_name,
            resolution,
            seed,
            name,
            _stats(map_fields[name]),
        )

    # Material response metadata. The material builder can consume these without
    # hard-coding species names, so generated bark sets remain self-describing.
    result["normal"]["trees2_normal_node_strength"] = 0.46
    result["height"]["trees2_bump_strength"] = 0.135
    result["height"]["trees2_bump_distance"] = 0.030
    return result


def _generate_bark(profile, pbr, seed, species, output):
    if str(species) != "WILLOW":
        return _PREVIOUS_GENERATE_BARK(profile, pbr, seed, species, output)
    return _generate_willow_bark(profile, pbr, seed, species, output)


def install():
    global _PREVIOUS_GENERATE_BARK, _INSTALLED
    if _INSTALLED:
        return
    from . import procedural_pbr

    _PREVIOUS_GENERATE_BARK = procedural_pbr._generate_bark
    procedural_pbr._generate_bark = _generate_bark
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    from . import procedural_pbr

    procedural_pbr._generate_bark = _PREVIOUS_GENERATE_BARK
    _INSTALLED = False
