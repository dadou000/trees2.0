"""Dedicated high-fidelity weeping-willow bark synthesis.

The generic bark generator is intentionally broad, but mature weeping willow
bark is dominated by irregular longitudinal strips, torn shoulders, deep riven
furrows and fine fibrous breakup.  A periodic sinusoidal furrow field reads as
wood grain rather than bark and becomes especially obvious at high resolution.

This module therefore replaces the bark generator only for WILLOW.  It uses a
periodic, non-uniform strip partition whose boundaries wander independently,
then builds nested fracture scales on top of that partition.  The output stays
seamless and uses the same Trees 2.0 PBR image/export pipeline.
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


# Quality changes structure complexity, not an upscale cap.  Willow is always
# evaluated at the requested texture resolution so a 4096 texture is a native
# 4096 structural solve instead of a 2048 field enlarged with bilinear filtering.
QUALITY = {
    "HIGH": dict(strip_extra=0, fracture_octaves=4, fibre_octaves=3),
    "ULTRA": dict(strip_extra=2, fracture_octaves=5, fibre_octaves=4),
    "EXTREME": dict(strip_extra=4, fracture_octaves=6, fibre_octaves=5),
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


def _normalize(field, lo=0.2, hi=99.8):
    low = float(np.percentile(field, lo))
    high = float(np.percentile(field, hi))
    if high - low <= 1.0e-8:
        return np.zeros_like(field, dtype=np.float32)
    return np.clip((field - low) / (high - low), 0.0, 1.0).astype(np.float32)


def _periodic_noise_1d(size, cells, rng):
    """Smooth periodic value noise without allocating a full 2-D field."""
    cells = max(2, int(cells))
    grid = rng.random(cells).astype(np.float32)
    coordinate = np.arange(size, dtype=np.float32) * (cells / float(size))
    i0 = np.floor(coordinate).astype(np.int32)
    t = coordinate - i0
    t = t * t * (3.0 - 2.0 * t)
    i1 = (i0 + 1) % cells
    i0 %= cells
    return (grid[i0] + (grid[i1] - grid[i0]) * t).astype(np.float32)


def _nonuniform_widths(count, rng):
    """Return positive periodic strip widths whose sum is exactly one."""
    # Log-normal-like variation creates broad and narrow bark ribbons without
    # allowing a single strip to consume most of the tile.
    raw = np.exp(rng.normal(0.0, 0.31, count)).astype(np.float32)
    raw = np.clip(raw, 0.54, 1.72)
    raw /= max(float(raw.sum()), 1.0e-8)
    return raw


def _strip_partition(size, count, rng, quality):
    """Build irregular vertical strips from independently wandering boundaries.

    Returns distance to the nearest/second-nearest furrow and an approximate
    local strip width.  This is the macro skeleton of the bark and deliberately
    contains no periodic sine band primitive.
    """
    widths = _nonuniform_widths(count, rng)
    boundaries = np.cumsum(widths)[:-1]
    # Include the seam boundary at zero.  All distances are periodic in X.
    boundaries = np.concatenate((np.asarray([0.0], dtype=np.float32), boundaries))

    x = np.arange(size, dtype=np.float32)[None, :] / float(size)
    d1 = np.full((size, size), 1.0, dtype=np.float32)
    d2 = np.full((size, size), 1.0, dtype=np.float32)

    for index, base in enumerate(boundaries):
        previous_width = float(widths[(index - 1) % count])
        next_width = float(widths[index % count])
        local_span = min(previous_width, next_width)

        # Independent periodic line wander.  Multiple value-noise bands produce
        # irregular kinks without a visible single-frequency waveform.
        low = _periodic_noise_1d(size, 3 + quality["strip_extra"] // 2, rng) - 0.5
        medium = _periodic_noise_1d(size, 8 + quality["strip_extra"], rng) - 0.5
        fine = _periodic_noise_1d(size, 19 + quality["strip_extra"] * 2, rng) - 0.5
        line = (
            float(base)
            + low * local_span * 0.25
            + medium * local_span * 0.105
            + fine * local_span * 0.035
        )
        line = np.mod(line, 1.0).astype(np.float32)

        delta = np.abs(x - line[:, None])
        distance = np.minimum(delta, 1.0 - delta).astype(np.float32)
        closer = distance < d1
        d2 = np.where(closer, d1, np.minimum(d2, distance))
        d1 = np.where(closer, distance, d1)

    strip_width = np.maximum(d1 + d2, 1.0 / float(max(size, 1)))
    # 0 at a furrow, ~1 at the strip centre.
    interior = np.clip(d1 / np.maximum(strip_width * 0.5, 1.0e-7), 0.0, 1.0)
    return d1.astype(np.float32), d2.astype(np.float32), strip_width.astype(np.float32), interior.astype(np.float32)


def _highpass(field, radius=1):
    blur = (
        np.roll(field, radius, axis=0)
        + np.roll(field, -radius, axis=0)
        + np.roll(field, radius, axis=1)
        + np.roll(field, -radius, axis=1)
    ) * 0.25
    return (field - blur).astype(np.float32)


def _local_contrast(height, amount=0.36):
    """Periodic unsharp height pass; no global blur is applied."""
    low = (
        np.roll(height, 1, axis=0)
        + np.roll(height, -1, axis=0)
        + np.roll(height, 1, axis=1)
        + np.roll(height, -1, axis=1)
        + np.roll(height, 2, axis=0)
        + np.roll(height, -2, axis=0)
        + np.roll(height, 2, axis=1)
        + np.roll(height, -2, axis=1)
    ) * 0.125
    return np.clip(height + (height - low) * float(amount), 0.0, 1.0).astype(np.float32)


def _build_willow_structure(profile, pbr, seed, resolution, quality_name):
    rng = np.random.default_rng(int(seed) ^ 0x57494C4C)  # 'WILL'
    quality = QUALITY.get(quality_name, QUALITY["ULTRA"])
    detail = float(pbr.bark_detail)

    # Mature willow has a modest number of major longitudinal ribbons.  The
    # species profile remains relevant but we deliberately avoid dozens of even
    # narrow furrows, which caused the synthetic striped appearance.
    profile_ridges = max(5, int(profile.get("ridge_count", 8)))
    strip_count = max(7, min(16, profile_ridges + quality["strip_extra"]))
    d1, _d2, strip_width, interior = _strip_partition(resolution, strip_count, rng, quality)

    # Broad strip body.  It rises quickly away from a crack but is not a smooth
    # cylindrical ridge; cellular/chunk fields break it into plates.
    body = _smoothstep(0.06, 0.72, interior)

    macro = bark_synthesis._fbm(
        resolution, max(3, strip_count // 3), 3,
        max(3, quality["fracture_octaves"] - 1), rng, 0.57,
    )
    chunks = bark_synthesis._fbm(
        resolution, max(6, strip_count), 8,
        quality["fracture_octaves"], rng, 0.52,
    )
    fracture_noise = bark_synthesis._fbm(
        resolution, max(18, strip_count * 3), 14,
        max(3, quality["fracture_octaves"] - 1), rng, 0.49,
    )

    # Vertically elongated cellular edges subdivide broad ribbons into broken
    # plates and introduce cross/diagonal interruptions seen on real old willow.
    plate, plate_edge = bark_synthesis._worley(
        resolution,
        max(10, strip_count * 2),
        10 + quality["strip_extra"],
        rng,
        stretch_x=1.18,
        stretch_y=0.58,
    )

    # Major furrows are narrow relative to the local strip width and receive a
    # ragged width modulation instead of a constant smooth stroke.
    rag = bark_synthesis._fbm(
        resolution, max(20, strip_count * 3), 13,
        max(3, quality["fracture_octaves"] - 1), rng, 0.47,
    )
    furrow_scale = strip_width * (0.052 + (rag - 0.5) * 0.022) + (0.65 / resolution)
    major_furrow = np.exp(-np.power(d1 / np.maximum(furrow_scale, 1.0e-7), 1.35)).astype(np.float32)
    major_furrow *= 0.68 + 0.32 * _smoothstep(0.18, 0.82, fracture_noise)
    major_furrow = _clamp01(major_furrow)

    # Raised shoulders right inside the main fissures.  Their amplitude is
    # broken by chunks, making peeling/torn lips rather than inflated tubes.
    shoulder = np.exp(-np.power((interior - 0.19) / 0.095, 2.0)).astype(np.float32)
    shoulder *= 0.42 + 0.58 * _smoothstep(0.28, 0.78, chunks)
    shoulder *= body

    # Secondary splits live inside the bark ribbons.  Cellular boundaries form
    # chunk edges; a high-frequency ridged field adds thin longitudinal tears.
    fracture_ridge = 1.0 - np.abs(fracture_noise * 2.0 - 1.0)
    thin_split = _smoothstep(0.79, 0.94, fracture_ridge)
    plate_split = _smoothstep(0.56, 0.91, plate_edge)
    split_gate = _smoothstep(0.20, 0.72, body) * (0.46 + 0.54 * _smoothstep(0.30, 0.74, chunks))
    internal_split = _clamp01((thin_split * 0.58 + plate_split * 0.68) * split_gate)

    # Fine anisotropic fibres.  Many cells across X but relatively few along Y
    # create the longitudinal dry grain missing from the old smooth result.
    fibre = bark_synthesis._fbm(
        resolution,
        max(64, strip_count * 9),
        10 + quality["strip_extra"],
        quality["fibre_octaves"],
        rng,
        0.47,
    )
    fibre_coarse = bark_synthesis._fbm(
        resolution,
        max(30, strip_count * 4),
        6 + quality["strip_extra"],
        max(2, quality["fibre_octaves"] - 1),
        rng,
        0.50,
    )
    fibrous_relief = (fibre - fibre_coarse).astype(np.float32)

    micro = bark_synthesis._fbm(
        resolution,
        max(110, strip_count * 12),
        37 + quality["strip_extra"] * 3,
        max(3, quality["fibre_octaves"] - 1),
        rng,
        0.44,
    )
    micro_hp = _highpass(micro, 1)

    ridge_depth = float(profile.get("ridge_depth", 0.24)) * detail
    crack_depth = float(profile.get("crack_depth", 0.34)) * detail
    fine_strength = float(profile.get("fine_strength", 0.09)) * detail

    height = np.full((resolution, resolution), 0.43, dtype=np.float32)
    height += body * (0.31 + ridge_depth * 0.26)
    height += (macro - 0.5) * 0.10
    height += (chunks - 0.5) * 0.145 * body
    height += (plate - 0.5) * 0.052 * body
    height += shoulder * (0.10 + ridge_depth * 0.16)
    height -= major_furrow * (0.39 + crack_depth * 0.34)
    height -= internal_split * (0.095 + crack_depth * 0.13)
    height += fibrous_relief * (0.105 + fine_strength * 0.35) * body
    height += micro_hp * (0.095 + fine_strength * 0.26) * body

    # Preserve the sharp shoulders and nested cracking.  This intentionally uses
    # percentile normalization + a local high-pass instead of a smoothing pass.
    height = _normalize(height, 0.12, 99.88)
    height = _local_contrast(height, 0.42 if quality_name == "EXTREME" else 0.34)

    crack = _clamp01(np.maximum(major_furrow, internal_split * 0.72))
    return {
        "height": height,
        "crack": crack,
        "major_furrow": major_furrow,
        "internal_split": internal_split,
        "interior": interior,
        "body": body,
        "shoulder": shoulder,
        "macro": macro.astype(np.float32),
        "chunks": chunks.astype(np.float32),
        "plate": plate.astype(np.float32),
        "plate_edge": plate_edge.astype(np.float32),
        "fibre": fibre.astype(np.float32),
        "fibrous_relief": fibrous_relief.astype(np.float32),
        "micro": micro.astype(np.float32),
        "style": "WILLOW_RIVEN_FIBROUS",
    }


def _derive_willow_ao(height, crack, resolution, strength):
    """Resolution-aware periodic cavity AO from several physical scales."""
    cavity = np.zeros_like(height, dtype=np.float32)
    # Radii scale with output resolution so 4096 retains broad-furrow AO rather
    # than using the same tiny 16-pixel neighbourhood as a 512 texture.
    scale = max(1, int(round(resolution / 1024.0)))
    samples = (
        (1 * scale, 0.18),
        (2 * scale, 0.17),
        (4 * scale, 0.16),
        (8 * scale, 0.15),
        (16 * scale, 0.13),
        (32 * scale, 0.11),
        (64 * scale, 0.10),
    )
    for radius, weight in samples:
        radius = max(1, min(resolution // 8, int(radius)))
        neighbors = (
            np.roll(height, radius, axis=0)
            + np.roll(height, -radius, axis=0)
            + np.roll(height, radius, axis=1)
            + np.roll(height, -radius, axis=1)
        ) * 0.25
        cavity += np.maximum(0.0, neighbors - height) * weight

    ao_strength = float(strength)
    ao = 1.0 - cavity * (3.8 + ao_strength * 5.1) - crack * ao_strength * 0.19
    return np.clip(ao, 0.20, 1.0).astype(np.float32)


def _colorize_willow(profile, fields, ao):
    height = fields["height"]
    crack = fields["crack"]
    chunks = fields["chunks"]
    fibre = fields["fibre"]
    shoulder = fields["shoulder"]
    micro = fields["micro"]

    base = np.asarray(profile.get("bark_base", (0.31, 0.27, 0.20)), dtype=np.float32)
    light = np.asarray(profile.get("bark_light", (0.46, 0.40, 0.30)), dtype=np.float32)
    dark = np.asarray(profile.get("bark_dark", (0.105, 0.080, 0.055)), dtype=np.float32)

    # Real mature willow is comparatively grey/brown.  Keep the species palette
    # but reduce saturation so the bark-color authority in the material receives
    # useful value structure rather than a muddy saturated brown image.
    base_gray = float(base.mean())
    light_gray = float(light.mean())
    dark_gray = float(dark.mean())
    base = base * 0.82 + base_gray * 0.18
    light = light * 0.80 + light_gray * 0.20
    dark = dark * 0.86 + dark_gray * 0.14

    tone = _clamp01(
        0.43
        + (height - 0.5) * 0.62
        + (chunks - 0.5) * 0.18
        + (fibre - 0.5) * 0.075
    )
    rgb = dark[None, None, :] + (light - dark)[None, None, :] * tone[..., None]
    rgb = rgb * 0.72 + base[None, None, :] * 0.28

    # Recessed fissures are darker/cooler; torn raised shoulders are dry and a
    # little lighter.  This separation helps the albedo reinforce actual relief.
    rgb *= 1.0 - crack[..., None] * 0.49
    dry = np.asarray((0.58, 0.50, 0.39), dtype=np.float32)
    shoulder_mask = np.clip(shoulder * (0.65 + 0.35 * height), 0.0, 1.0)[..., None]
    rgb = rgb * (1.0 - shoulder_mask * 0.11) + dry[None, None, :] * shoulder_mask * 0.11

    # Fine weathering/pore variation, intentionally high-frequency enough to be
    # visible at 2K/4K without becoming noisy from normal viewing distances.
    weather = _smoothstep(0.68, 0.91, micro)[..., None]
    gray = rgb.mean(axis=2, keepdims=True)
    rgb = rgb * (1.0 - weather * 0.09) + gray * weather * 0.09
    rgb *= (0.90 + 0.10 * ao[..., None])
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def _rgba_rgb(rgb):
    height, width, _ = rgb.shape
    out = np.empty((height, width, 4), dtype=np.float32)
    out[..., :3] = rgb
    out[..., 3] = 1.0
    return array("f", out.reshape(-1))


def _rgba_gray(gray):
    height, width = gray.shape
    out = np.empty((height, width, 4), dtype=np.float32)
    out[..., 0] = gray
    out[..., 1] = gray
    out[..., 2] = gray
    out[..., 3] = 1.0
    return array("f", out.reshape(-1))


def _rgba_normal(normals):
    nx, ny, nz = normals
    height, width = nx.shape
    out = np.empty((height, width, 4), dtype=np.float32)
    out[..., 0] = nx
    out[..., 1] = ny
    out[..., 2] = nz
    out[..., 3] = 1.0
    return array("f", out.reshape(-1))


def _generate_willow_bark(profile, pbr, seed, species, output):
    if np is None:
        return _PREVIOUS_GENERATE_BARK(profile, pbr, seed, species, output)

    from . import procedural_pbr

    resolution = int(pbr.bark_resolution)
    quality_name = str(getattr(pbr, "bark_quality", "ULTRA"))
    fields = _build_willow_structure(profile, pbr, seed, resolution, quality_name)

    height = fields["height"]
    ao = _derive_willow_ao(
        height,
        fields["crack"],
        resolution,
        profile.get("ao_strength", 0.46),
    )
    normals = bark_synthesis._derive_normal(
        height,
        pbr.bark_normal_strength,
        profile.get("bark_normal_strength", 4.2),
    )
    rgb = _colorize_willow(profile, fields, ao)

    base_roughness = float(profile.get("bark_roughness", 0.84))
    cavity = 1.0 - ao
    fibre_detail = np.abs(fields["fibrous_relief"])
    ridge_exposure = _smoothstep(0.64, 0.90, height)
    roughness = (
        base_roughness
        + fields["crack"] * 0.070
        + cavity * 0.095
        + fibre_detail * 0.16
        + (fields["micro"] - 0.5) * 0.050
        - ridge_exposure * 0.028
    )
    roughness = np.clip(roughness, 0.61, 0.995).astype(np.float32)

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

    for image in result.values():
        image["trees2_bark_generator"] = "WILLOW_RIVEN_V3"
        image["trees2_bark_style"] = "WILLOW_RIVEN_FIBROUS"
        image["trees2_bark_quality"] = quality_name
        image["trees2_bark_native_resolution"] = resolution
        image["trees2_bark_seed"] = int(seed)
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

    # bark_synthesis.install() must run first; this wrapper then receives the HQ
    # generator as its fallback for every non-willow species.
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
