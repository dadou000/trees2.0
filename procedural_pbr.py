import math
import random
from array import array
from pathlib import Path

import bpy

from .pbr_profiles import species_profile
from .species_appearance import appearance_profile


TAU = math.tau


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _mix(a, b, t):
    return a * (1.0 - t) + b * t


def _mix3(a, b, t):
    return tuple(_mix(a[i], b[i], t) for i in range(3))


def _smoothstep(a, b, x):
    if abs(b - a) < 1e-8:
        return 1.0 if x >= b else 0.0
    t = _clamp((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


def _safe_name(value):
    return "".join(c.lower() if c.isalnum() else "_" for c in str(value)).strip("_")


def _output_directory(settings):
    raw = bpy.path.abspath(settings.output_directory)
    if settings.output_directory.startswith("//") and not bpy.data.filepath:
        raw = str(Path(bpy.app.tempdir) / "Trees2_PBR")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _new_image(name, width, height, pixels, filepath, non_color=False, pack=False):
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old, do_unlink=True)
    image = bpy.data.images.new(name=name, width=width, height=height, alpha=True, float_buffer=False)
    image.pixels.foreach_set(pixels)
    if non_color:
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
    image.filepath_raw = str(filepath)
    image.file_format = "PNG"
    image["trees2_generated_pbr"] = True
    image.save()
    if pack:
        try:
            image.pack()
        except Exception:
            pass
    return image


def _distance_to_segment(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    denom = vx * vx + vy * vy
    t = 0.0 if denom <= 1e-9 else _clamp((wx * vx + wy * vy) / denom)
    dx = px - (ax + vx * t)
    dy = py - (ay + vy * t)
    return math.sqrt(dx * dx + dy * dy)


def _leaf_record(cx, cy, angle, sx, sy, shape, tone, stem_x=0.0, stem_y=-0.72):
    return {
        "cx": cx, "cy": cy, "angle": angle,
        "sx": sx, "sy": sy, "shape": shape, "tone": tone,
        "stem_x": stem_x, "stem_y": stem_y,
    }


def _variant_leaves(profile, rng):
    kind = profile["leaf_shape"]
    arrangement = profile.get("arrangement", "CLUSTER")
    count = int(profile["leaf_count"])
    aspect = max(float(profile.get("leaf_aspect", 1.35)), 0.35)
    leaflet_scale = float(profile.get("leaflet_scale", 1.0))
    if kind == "NONE" or arrangement == "NONE" or count <= 0:
        return []

    leaves = []

    if arrangement == "PINNATE":
        pairs = max(2, (count - 1) // 2)
        for i in range(pairs):
            y = -0.43 + i * (0.76 / max(1, pairs - 1))
            spread = 0.18 + 0.04 * math.sin(i * 1.7)
            for side in (-1.0, 1.0):
                angle = side * rng.uniform(0.72, 1.02)
                sy = rng.uniform(0.20, 0.27) * leaflet_scale
                sx = sy / aspect
                leaves.append(_leaf_record(
                    side * spread, y + rng.uniform(-0.02, 0.02), angle,
                    sx, sy, kind, rng.uniform(-0.09, 0.09), 0.0, y - 0.03,
                ))
        sy = 0.27 * leaflet_scale
        leaves.append(_leaf_record(0.0, 0.54, 0.0, sy / aspect, sy, kind,
                                   rng.uniform(-0.08, 0.08), 0.0, 0.32))
        return leaves

    if arrangement == "BIPINNATE":
        # Two-level rachis: several side pinnules, each carrying tiny paired leaflets.
        pinnules = 4
        per_pinnule = max(2, count // (pinnules * 2))
        for pi in range(pinnules):
            py = -0.36 + pi * 0.23
            for side in (-1.0, 1.0):
                branch_angle = side * rng.uniform(0.70, 0.92)
                dx = math.sin(branch_angle)
                dy = math.cos(branch_angle)
                for li in range(per_pinnule):
                    t = (li + 1) / (per_pinnule + 0.5)
                    center_x = side * 0.055 + dx * t * 0.36
                    center_y = py + dy * t * 0.36
                    leaflet_side = -1.0 if li % 2 else 1.0
                    angle = branch_angle + leaflet_side * rng.uniform(0.45, 0.70)
                    sy = rng.uniform(0.095, 0.135) * leaflet_scale
                    leaves.append(_leaf_record(
                        center_x, center_y, angle, sy / aspect, sy, kind,
                        rng.uniform(-0.10, 0.10),
                        side * 0.055 + dx * max(0.0, t - 0.18) * 0.36,
                        py + dy * max(0.0, t - 0.18) * 0.36,
                    ))
        return leaves

    if arrangement == "PALMATE_COMPOUND":
        for i in range(max(5, count)):
            t = i / max(1, count - 1)
            angle = -1.02 + 2.04 * t + rng.uniform(-0.08, 0.08)
            radial = rng.uniform(0.28, 0.36)
            cx = math.sin(angle) * radial
            cy = -0.05 + math.cos(angle) * radial * 0.62
            sy = rng.uniform(0.27, 0.34) * leaflet_scale
            leaves.append(_leaf_record(
                cx, cy, angle, sy / aspect, sy, kind, rng.uniform(-0.09, 0.09),
                0.0, -0.12,
            ))
        return leaves

    if arrangement == "NEEDLE_FASCICLE":
        fascicle_size = max(2, int(profile.get("fascicle_size", 2)))
        groups = max(3, count // fascicle_size)
        for gi in range(groups):
            y = -0.45 + gi * (0.84 / max(1, groups - 1))
            side = -1.0 if gi % 2 else 1.0
            anchor_x = side * rng.uniform(0.035, 0.10)
            for ni in range(fascicle_size):
                angle = side * rng.uniform(0.65, 1.05) + (ni - (fascicle_size - 1) * 0.5) * 0.15
                sy = rng.uniform(0.30, 0.42)
                sx = rng.uniform(0.018, 0.032)
                leaves.append(_leaf_record(anchor_x, y, angle, sx, sy, "NEEDLE",
                                           rng.uniform(-0.08, 0.08), 0.0, y - 0.03))
        return leaves

    if arrangement == "NEEDLE_RADIAL":
        for i in range(count):
            t = i / max(1, count - 1)
            y = -0.52 + 1.00 * t
            phase = (i % 5) / 5.0 * TAU
            side = math.sin(phase)
            angle = side * rng.uniform(0.70, 1.25)
            sy = rng.uniform(0.18, 0.28)
            leaves.append(_leaf_record(side * 0.06, y, angle, rng.uniform(0.018, 0.030), sy,
                                       "NEEDLE", rng.uniform(-0.08, 0.08), 0.0, y))
        return leaves

    if arrangement == "NEEDLE_FLAT":
        for i in range(count):
            t = i / max(1, count - 1)
            y = -0.50 + 0.96 * t
            side = -1.0 if i % 2 else 1.0
            angle = side * rng.uniform(1.05, 1.35) + rng.uniform(-0.08, 0.08)
            sy = rng.uniform(0.18, 0.29)
            leaves.append(_leaf_record(side * 0.045, y, angle, rng.uniform(0.020, 0.034), sy,
                                       "NEEDLE", rng.uniform(-0.07, 0.07), 0.0, y))
        return leaves

    if arrangement == "NEEDLE_ROSETTE":
        rosettes = 4
        per = max(4, count // rosettes)
        for ri in range(rosettes):
            ay = -0.42 + ri * 0.28
            ax = (-1.0 if ri % 2 else 1.0) * 0.045
            for ni in range(per):
                angle = (ni / per) * TAU + rng.uniform(-0.10, 0.10)
                sy = rng.uniform(0.16, 0.25)
                leaves.append(_leaf_record(ax, ay, angle, rng.uniform(0.020, 0.032), sy,
                                           "NEEDLE", rng.uniform(-0.07, 0.07), ax, ay))
        return leaves

    if arrangement == "SCALE_SPRAY":
        for i in range(count):
            t = i / max(1, count - 1)
            y = -0.52 + 1.02 * t
            side = -1.0 if i % 2 else 1.0
            angle = side * rng.uniform(0.55, 0.92)
            leaves.append(_leaf_record(
                side * rng.uniform(0.04, 0.11), y, angle,
                rng.uniform(0.045, 0.070), rng.uniform(0.10, 0.16), "SCALE",
                rng.uniform(-0.08, 0.08), 0.0, y - 0.02,
            ))
        return leaves

    # Normal broadleaf cluster.
    base_count = max(1, count)
    for i in range(base_count):
        a = TAU * (i / base_count) + rng.uniform(-0.38, 0.38)
        radial = rng.uniform(0.14, 0.42)
        cx = math.sin(a) * radial * 0.75
        cy = math.cos(a) * radial * 0.55 + rng.uniform(-0.05, 0.08)
        angle = -a * 0.40 + rng.uniform(-0.45, 0.45)
        sy = rng.uniform(0.34, 0.48)
        sx = sy / aspect
        leaves.append(_leaf_record(cx, cy, angle, sx, sy, kind,
                                   rng.uniform(-0.12, 0.12)))
    return leaves


def _leaf_half_width(kind, v, profile):
    av = abs(v)
    if av >= 1.0:
        return 0.0

    if kind == "NEEDLE":
        return max(0.025, 0.16 * (1.0 - av) ** 0.32)
    if kind == "LANCE":
        return 0.78 * max(0.0, 1.0 - av ** 1.28) ** 0.58
    if kind == "ROUND":
        return math.sqrt(max(0.0, 1.0 - v * v))
    if kind == "DELTOID":
        t = _clamp((v + 1.0) * 0.5)
        return _clamp(2.25 * (t ** 0.56) * ((1.0 - t) ** 0.78))
    if kind == "HEART":
        base = math.sqrt(max(0.0, 1.0 - v * v))
        return base * (1.0 + 0.18 * (1.0 - v) * 0.5)

    base = max(0.0, 1.0 - av ** 1.70) ** 0.52
    if kind == "ELLIPTIC_POINTED":
        sharp = float(profile.get("tip_sharpness", 0.55))
        tip_factor = 1.0 - sharp * 0.30 * _smoothstep(0.25, 0.95, v)
        return base * tip_factor
    if kind == "OAK_LOBED":
        lobes = max(4, int(profile.get("lobes", 5)))
        depth = _clamp(float(profile.get("lobe_depth", 0.45)))
        # Multiple paired lobes separated by deep rounded sinuses along the axis.
        phase = (v + 0.82) * math.pi * max(2.0, lobes - 1.0)
        lobe_wave = 0.5 + 0.5 * math.cos(phase)
        return base * (1.0 - depth * 0.48 * (1.0 - lobe_wave))
    return base


def _leaf_alpha(kind, u, v, profile, detail):
    asym = float(profile.get("asymmetry", 0.0))
    u += asym * 0.16 * (1.0 - v * v)

    if kind == "PALMATE":
        r = math.sqrt((u * 0.96) ** 2 + (v * 0.94) ** 2)
        theta = math.atan2(u, v)
        lobes = max(5, int(profile.get("lobes", 5)))
        depth = _clamp(float(profile.get("lobe_depth", 0.55)))
        major = (0.5 + 0.5 * math.cos(lobes * theta)) ** 1.85
        boundary = (0.50 - depth * 0.08) + (0.28 + depth * 0.22) * major
        # Slightly emphasize the terminal lobe.
        boundary += max(0.0, v) * 0.08
        return _smoothstep(0.042, -0.012, r - boundary)

    if kind == "SCALE":
        margin = 1.0 - (abs(u) * 1.10 + abs(v) * 0.92)
        return _smoothstep(0.0, 0.10, margin)

    half = _leaf_half_width(kind, v, profile)
    if half <= 0.0:
        return 0.0

    serr = float(profile.get("serration", 0.0)) * detail
    if serr > 0.0 and kind not in {"NEEDLE", "SCALE"}:
        teeth = 8.0 + 26.0 * _clamp(serr)
        tooth_wave = abs(math.sin((v + 1.0) * math.pi * teeth))
        half *= 1.0 + serr * 0.12 * (0.55 - tooth_wave)

    margin = half - abs(u)
    alpha = _smoothstep(0.0, 0.043, margin) * _smoothstep(0.0, 0.035, 1.0 - abs(v))

    if kind == "HEART":
        notch_strength = float(profile.get("base_notch", 0.72))
        if v < -0.48:
            notch = math.exp(-((u / 0.18) ** 2 + ((v + 0.88) / 0.16) ** 2))
            alpha *= 1.0 - notch_strength * notch

    return _clamp(alpha)


def _leaf_sample(x, y, leaf, profile, pbr, rng_seed):
    ca = math.cos(leaf["angle"])
    sa = math.sin(leaf["angle"])
    dx, dy = x - leaf["cx"], y - leaf["cy"]
    u = (ca * dx + sa * dy) / max(leaf["sx"], 1e-5)
    v = (-sa * dx + ca * dy) / max(leaf["sy"], 1e-5)
    a = _leaf_alpha(leaf["shape"], u, v, profile, pbr.leaf_detail)
    if a <= 0.001:
        return None

    damage = float(profile.get("leaf_damage", 0.0)) * pbr.leaf_detail
    if damage > 0.0 and leaf["shape"] not in {"NEEDLE", "SCALE"}:
        hx = math.sin(rng_seed * 1.371) * 0.42
        hy = math.cos(rng_seed * 0.917) * 0.45
        hr = 0.05 + damage * 0.22
        if (u - hx) ** 2 + (v - hy) ** 2 < hr * hr:
            a *= 0.08

    if leaf["shape"] in {"NEEDLE", "SCALE"}:
        mid = math.exp(-((abs(u) * 8.0) ** 2)) * 0.35
        secondary = 0.0
    else:
        mid = math.exp(-((abs(u) * 15.0) ** 2))
        sec_wave = abs(math.sin((abs(v) * 5.5 + abs(u) * 1.6) * math.pi))
        secondary = math.exp(-((sec_wave / 0.18) ** 2)) * (1.0 - _clamp(abs(u))) * 0.34
    vein = _clamp(mid + secondary)

    tone = _clamp(0.46 + 0.24 * v + leaf["tone"])
    color = _mix3(profile["leaf_color"], profile["leaf_color_2"], tone)
    color = _mix3(color, profile["vein_color"], vein * 0.28)

    strength = float(profile["leaf_normal_strength"]) * pbr.leaf_normal_strength
    nx = -u * strength * 0.34 + math.copysign(mid * 0.06 * strength, u if abs(u) > 1e-5 else 1.0)
    ny = -v * strength * 0.10 + (secondary - 0.10) * 0.04 * strength
    gx = ca * nx - sa * ny
    gy = sa * nx + ca * ny
    nz = 1.0
    inv = 1.0 / math.sqrt(gx * gx + gy * gy + nz * nz)
    normal = (gx * inv * 0.5 + 0.5, gy * inv * 0.5 + 0.5, nz * inv * 0.5 + 0.5)
    rough = _clamp(float(profile["leaf_roughness"]) - vein * 0.05 + abs(u) * 0.025 + leaf["tone"] * 0.04)
    return a, color, normal, rough


def _generate_leaf_atlas(profile, pbr, seed, species, output):
    resolution = int(pbr.leaf_resolution)
    grid = int(pbr.atlas_grid)
    variants = grid * grid
    rng = random.Random(seed ^ 0x29A3D781)
    variant_data = [_variant_leaves(profile, random.Random(rng.randrange(2**31))) for _ in range(variants)]

    albedo = array("f")
    normal = array("f")
    roughness = array("f")
    cell = resolution / grid

    for py in range(resolution):
        row_from_bottom = min(grid - 1, int(py / cell))
        row = grid - 1 - row_from_bottom
        ly = ((py - row_from_bottom * cell) / cell) * 2.0 - 1.0
        for px in range(resolution):
            col = min(grid - 1, int(px / cell))
            lx = ((px - col * cell) / cell) * 2.0 - 1.0
            variant = row * grid + col
            leaves = variant_data[variant]

            best = None
            for li, leaf in enumerate(leaves):
                sample = _leaf_sample(lx, ly, leaf, profile, pbr, seed + variant * 101 + li * 17)
                if sample and (best is None or sample[0] >= best[0]):
                    best = sample

            twig_alpha = 0.0
            if leaves:
                for leaf in leaves:
                    direction = (math.sin(leaf["angle"]), math.cos(leaf["angle"]))
                    bx = leaf["cx"] - direction[0] * leaf["sy"] * 0.72
                    by = leaf["cy"] - direction[1] * leaf["sy"] * 0.72
                    d = _distance_to_segment(
                        lx, ly,
                        float(leaf.get("stem_x", 0.0)), float(leaf.get("stem_y", -0.72)),
                        bx, by,
                    )
                    twig_alpha = max(twig_alpha, _smoothstep(0.028, 0.008, d))

            if best is None and twig_alpha <= 0.001:
                albedo.extend((0.0, 0.0, 0.0, 0.0))
                normal.extend((0.5, 0.5, 1.0, 1.0))
                roughness.extend((1.0, 1.0, 1.0, 1.0))
                continue

            if best is None or twig_alpha > best[0] * 1.08:
                color = profile["twig_color"]
                a = twig_alpha
                n = (0.5, 0.5, 1.0)
                rgh = 0.86
            else:
                a, color, n, rgh = best
                a = max(a, twig_alpha * 0.65)

            albedo.extend((color[0], color[1], color[2], a))
            normal.extend((n[0], n[1], n[2], 1.0))
            roughness.extend((rgh, rgh, rgh, 1.0))

    stem = f"trees2_{_safe_name(species)}_{seed}_leaf"
    return {
        "albedo": _new_image(f"{stem}_albedo", resolution, resolution, albedo,
                             output / f"{stem}_albedo.png", False, pbr.pack_images),
        "normal": _new_image(f"{stem}_normal", resolution, resolution, normal,
                             output / f"{stem}_normal.png", True, pbr.pack_images),
        "roughness": _new_image(f"{stem}_roughness", resolution, resolution, roughness,
                                output / f"{stem}_roughness.png", True, pbr.pack_images),
    }


def _bark_fields(profile, pbr, resolution, seed):
    rng = random.Random(seed ^ 0x6C8E9CF5)
    phase1, phase2, phase3 = (rng.uniform(0.0, TAU) for _ in range(3))
    ridge_n = max(1, int(profile["ridge_count"]))
    crack_n = max(1, int(profile["crack_count"]))
    plate_n = max(1, int(profile["plate_scale"]))
    detail = float(pbr.bark_detail)
    heights = array("f", [0.0]) * (resolution * resolution)
    cracks = array("f", [0.0]) * (resolution * resolution)
    fines = array("f", [0.0]) * (resolution * resolution)

    for y in range(resolution):
        fy = y / resolution
        warp = 0.055 * math.sin(TAU * fy + phase1) + 0.025 * math.sin(TAU * 3.0 * fy + phase2)
        for x in range(resolution):
            fx = x / resolution
            wx = fx + warp
            ridge = 0.5 + 0.5 * math.sin(TAU * ridge_n * wx + 0.55 * math.sin(TAU * 2.0 * fy + phase2))
            crack_wave = abs(math.sin(TAU * crack_n * wx + 0.42 * math.sin(TAU * 5.0 * fy + phase3)))
            crack = math.exp(-crack_wave * (12.0 + 5.0 * detail))
            plate = 0.5 + 0.25 * math.sin(TAU * plate_n * fx + phase2) + 0.25 * math.sin(TAU * (plate_n + 1) * fy + phase3)
            fine = 0.5 + 0.25 * math.sin(TAU * 23.0 * fx + phase1) + 0.25 * math.sin(TAU * 19.0 * fy + phase2)
            h = 0.48 + (ridge - 0.5) * float(profile["ridge_depth"]) * detail
            h += (plate - 0.5) * 0.18 * detail
            h += (fine - 0.5) * float(profile["fine_strength"]) * detail
            h -= crack * float(profile["crack_depth"]) * detail
            i = y * resolution + x
            heights[i] = _clamp(h)
            cracks[i] = _clamp(crack)
            fines[i] = _clamp(fine)
    return heights, cracks, fines


def _generate_bark(profile, pbr, seed, species, output):
    resolution = int(pbr.bark_resolution)
    height_values, cracks, fines = _bark_fields(profile, pbr, resolution, seed)
    albedo = array("f")
    normal = array("f")
    roughness = array("f")
    height_map = array("f")
    ao = array("f")
    normal_strength = float(profile["bark_normal_strength"]) * pbr.bark_normal_strength

    for y in range(resolution):
        ym = (y - 1) % resolution
        yp = (y + 1) % resolution
        for x in range(resolution):
            xm = (x - 1) % resolution
            xp = (x + 1) % resolution
            i = y * resolution + x
            h = height_values[i]
            crack = cracks[i]
            fine = fines[i]
            dx = (height_values[y * resolution + xp] - height_values[y * resolution + xm]) * normal_strength
            dy = (height_values[yp * resolution + x] - height_values[ym * resolution + x]) * normal_strength
            nx, ny, nz = -dx, -dy, 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)

            color = _mix3(profile["bark_dark"], profile["bark_light"], _clamp(h * 0.90 + 0.05))
            color = _mix3(color, profile["bark_dark"], crack * 0.72)
            moss = float(profile.get("moss", 0.0)) * _smoothstep(0.25, 0.75, fine)
            if moss > 0.0:
                color = _mix3(color, (0.17, 0.24, 0.08), moss)
            rgh = _clamp(float(profile["bark_roughness"]) + crack * 0.07 + (0.5 - fine) * 0.05)
            occ = _clamp(1.0 - crack * float(profile["ao_strength"]) - max(0.0, 0.42 - h) * 0.55)

            albedo.extend((color[0], color[1], color[2], 1.0))
            normal.extend((nx * inv * 0.5 + 0.5, ny * inv * 0.5 + 0.5, nz * inv * 0.5 + 0.5, 1.0))
            roughness.extend((rgh, rgh, rgh, 1.0))
            height_map.extend((h, h, h, 1.0))
            ao.extend((occ, occ, occ, 1.0))

    stem = f"trees2_{_safe_name(species)}_{seed}_bark"
    return {
        "albedo": _new_image(f"{stem}_albedo", resolution, resolution, albedo,
                             output / f"{stem}_albedo.png", False, pbr.pack_images),
        "normal": _new_image(f"{stem}_normal", resolution, resolution, normal,
                             output / f"{stem}_normal.png", True, pbr.pack_images),
        "roughness": _new_image(f"{stem}_roughness", resolution, resolution, roughness,
                                output / f"{stem}_roughness.png", True, pbr.pack_images),
        "height": _new_image(f"{stem}_height", resolution, resolution, height_map,
                             output / f"{stem}_height.png", True, pbr.pack_images),
        "ao": _new_image(f"{stem}_ao", resolution, resolution, ao,
                         output / f"{stem}_ao.png", True, pbr.pack_images),
    }


def generate_species_pbr(context, species=None):
    settings = context.scene.trees2_settings
    pbr = context.scene.trees2_pbr_settings
    species = species or settings.species_preset
    profile = appearance_profile(species, species_profile(species))
    seed = int(settings.seed) ^ int(pbr.seed_offset) ^ 0x13579BDF
    output = _output_directory(pbr) / _safe_name(species)
    output.mkdir(parents=True, exist_ok=True)

    result = {
        "species": species,
        "morphology": profile.get("morphology_label", profile.get("leaf_shape", "Unknown")),
        "output": str(output),
        "leaf": None,
        "bark": None,
    }
    if pbr.generate_leaves and profile["leaf_shape"] != "NONE":
        result["leaf"] = _generate_leaf_atlas(profile, pbr, seed, species, output)
    if pbr.generate_bark:
        result["bark"] = _generate_bark(profile, pbr, seed, species, output)

    if pbr.auto_assign:
        if result["leaf"]:
            settings.leaf_image = result["leaf"]["albedo"]
            settings.leaf_normal_image = result["leaf"]["normal"]
            settings.leaf_roughness_image = result["leaf"]["roughness"]
            settings.atlas_columns = int(pbr.atlas_grid)
            settings.atlas_rows = int(pbr.atlas_grid)
            settings.atlas_variants = int(pbr.atlas_grid) ** 2
        elif profile["leaf_shape"] == "NONE":
            settings.leaf_image = None
            settings.leaf_normal_image = None
            settings.leaf_roughness_image = None
        if result["bark"]:
            settings.bark_image = result["bark"]["albedo"]
            settings.bark_normal_image = result["bark"]["normal"]
            settings.bark_roughness_image = result["bark"]["roughness"]
            settings.bark_height_image = result["bark"]["height"]
            settings.bark_ao_image = result["bark"]["ao"]

        # Raw-albedo mode remains available for backwards compatibility, but
        # the default keeps the preset/user colors authoritative.
        if pbr.neutralize_tints:
            settings.pbr_respect_tree_colors = False
        else:
            settings.pbr_respect_tree_colors = True
    return result


class TREES2_OT_GenerateProceduralPBR(bpy.types.Operator):
    bl_idname = "trees2.generate_procedural_pbr"
    bl_label = "Generate Species PBR"
    bl_description = "Generate species-correct leaf/needle silhouettes and bark PBR maps"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            result = generate_species_pbr(context)
        except Exception as exc:
            self.report({"ERROR"}, f"PBR generation failed: {exc}")
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Generated {result['species']} ({result['morphology']}) PBR textures in {result['output']}",
        )
        return {"FINISHED"}


class TREES2_OT_OpenPBRFolder(bpy.types.Operator):
    bl_idname = "trees2.open_pbr_folder"
    bl_label = "Open Output Folder"
    bl_description = "Open the procedural PBR output folder"

    def execute(self, context):
        path = _output_directory(context.scene.trees2_pbr_settings)
        try:
            bpy.ops.wm.path_open(filepath=str(path))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (TREES2_OT_GenerateProceduralPBR, TREES2_OT_OpenPBRFolder)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
