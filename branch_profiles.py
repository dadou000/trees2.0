import math

import bpy

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


PROFILE_PRESETS = {
    "BROADLEAF": {
        "hold_thickness": 0.86,
        "taper_start": 0.72,
        "tip_ratio": 0.045,
        "taper_curve": 1.90,
        "radius_variation": 0.065,
        "base_swell": 0.10,
        "primary": (0.56, 0.72),
        "secondary": (0.43, 0.58),
        "tertiary": (0.34, 0.48),
        "level_taper_shift": 0.032,
        "level_hold_loss": 0.022,
        "branch_variation": 0.08,
    },
    "OAK": {
        "hold_thickness": 0.91,
        "taper_start": 0.78,
        "tip_ratio": 0.055,
        "taper_curve": 2.20,
        "radius_variation": 0.095,
        "base_swell": 0.16,
        "primary": (0.64, 0.80),
        "secondary": (0.48, 0.64),
        "tertiary": (0.38, 0.54),
        "level_taper_shift": 0.028,
        "level_hold_loss": 0.018,
        "branch_variation": 0.11,
    },
    "BIRCH": {
        "hold_thickness": 0.80,
        "taper_start": 0.66,
        "tip_ratio": 0.035,
        "taper_curve": 1.55,
        "radius_variation": 0.045,
        "base_swell": 0.06,
        "primary": (0.48, 0.64),
        "secondary": (0.38, 0.52),
        "tertiary": (0.30, 0.44),
        "level_taper_shift": 0.040,
        "level_hold_loss": 0.030,
        "branch_variation": 0.07,
    },
    "WILLOW": {
        "hold_thickness": 0.76,
        "taper_start": 0.60,
        "tip_ratio": 0.028,
        "taper_curve": 1.35,
        "radius_variation": 0.050,
        "base_swell": 0.06,
        "primary": (0.46, 0.60),
        "secondary": (0.35, 0.49),
        "tertiary": (0.27, 0.40),
        "level_taper_shift": 0.045,
        "level_hold_loss": 0.034,
        "branch_variation": 0.08,
    },
    "CONIFER": {
        "hold_thickness": 0.83,
        "taper_start": 0.69,
        "tip_ratio": 0.035,
        "taper_curve": 1.70,
        "radius_variation": 0.040,
        "base_swell": 0.07,
        "primary": (0.42, 0.60),
        "secondary": (0.34, 0.48),
        "tertiary": (0.28, 0.40),
        "level_taper_shift": 0.038,
        "level_hold_loss": 0.028,
        "branch_variation": 0.06,
    },
}


OAK_SPECIES = {
    "OAK", "HOLM_OAK", "CORK_OAK", "CHESTNUT", "WALNUT", "PLANE",
    "APPLE", "OLIVE", "BAOBAB",
}
BIRCH_SPECIES = {
    "BIRCH", "ALDER", "ASPEN", "POPLAR", "JACARANDA", "EUCALYPTUS",
}
WILLOW_SPECIES = {"WILLOW"}
CONIFER_SPECIES = {
    "PINE", "STONE_PINE", "SPRUCE", "FIR", "CEDAR", "CYPRESS", "REDWOOD",
}


def _stable_unit(seed, value):
    x = (int(seed) ^ int(value) ^ 0xA511E9B3) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def _auto_profile_name(species):
    species = str(species)
    if species in OAK_SPECIES:
        return "OAK"
    if species in BIRCH_SPECIES:
        return "BIRCH"
    if species in WILLOW_SPECIES:
        return "WILLOW"
    if species in CONIFER_SPECIES:
        return "CONIFER"
    return "BROADLEAF"


def _manual_profile(profile):
    primary = sorted((profile.primary_radius_min, profile.primary_radius_max))
    secondary = sorted((profile.secondary_radius_min, profile.secondary_radius_max))
    tertiary = sorted((profile.tertiary_radius_min, profile.tertiary_radius_max))
    return {
        "hold_thickness": profile.hold_thickness,
        "taper_start": profile.taper_start,
        "tip_ratio": profile.tip_ratio,
        "taper_curve": profile.taper_curve,
        "radius_variation": profile.radius_variation,
        "base_swell": profile.base_swell,
        "primary": tuple(primary),
        "secondary": tuple(secondary),
        "tertiary": tuple(tertiary),
        "level_taper_shift": profile.level_taper_shift,
        "level_hold_loss": profile.level_hold_loss,
        "branch_variation": profile.branch_variation,
    }


def effective_profile(settings, profile_settings):
    preset = profile_settings.profile_preset
    if preset == "AUTO":
        preset = _auto_profile_name(settings.species_preset)
    if preset == "CUSTOM":
        values = _manual_profile(profile_settings)
    else:
        values = dict(PROFILE_PRESETS.get(preset, PROFILE_PRESETS["BROADLEAF"]))
    values["resolved_name"] = preset
    return values


def _nearest_parent_radius(parent, position):
    points = parent.get("points", ())
    if len(points) < 2:
        return points[0][1] if points else 0.0

    best_d2 = float("inf")
    best_radius = float(points[0][1])
    for i in range(len(points) - 1):
        p0, r0 = points[i]
        p1, r1 = points[i + 1]
        edge = p1 - p0
        denom = edge.length_squared
        if denom <= 1e-12:
            t = 0.0
        else:
            t = max(0.0, min(1.0, (position - p0).dot(edge) / denom))
        closest = p0.lerp(p1, t)
        d2 = (position - closest).length_squared
        if d2 < best_d2:
            best_d2 = d2
            best_radius = float(r0) * (1.0 - t) + float(r1) * t
    return best_radius


def _ratio_range(values, level):
    if level <= 1:
        return values["primary"]
    if level == 2:
        return values["secondary"]
    lo, hi = values["tertiary"]
    decay = 0.93 ** max(0, level - 3)
    return lo * decay, hi * decay


def _radius_profile(t, base_radius, values, level, branch_seed, collar, parent_radius):
    t = max(0.0, min(1.0, t))
    variation = values["branch_variation"]

    v0 = _stable_unit(branch_seed, 17)
    v1 = _stable_unit(branch_seed, 31)
    v2 = _stable_unit(branch_seed, 47)
    v3 = _stable_unit(branch_seed, 71)

    hold = values["hold_thickness"]
    hold *= 1.0 + (v0 - 0.5) * variation * 0.70
    hold -= max(0, level - 1) * values["level_hold_loss"]
    hold = max(0.48, min(0.97, hold))

    taper_start = values["taper_start"]
    taper_start += (v1 - 0.5) * variation * 0.45
    taper_start -= max(0, level - 1) * values["level_taper_shift"]
    taper_start = max(0.34, min(0.92, taper_start))

    tip = values["tip_ratio"] * (0.88 + 0.24 * v2)
    taper_curve = values["taper_curve"] * (0.88 + 0.24 * v3)

    if t <= taper_start:
        x = t / max(taper_start, 1e-6)
        core = 1.0 - (1.0 - hold) * (x ** 1.45)
    else:
        x = (t - taper_start) / max(1.0 - taper_start, 1e-6)
        drop = x ** taper_curve
        core = hold * (1.0 - drop) + tip * drop

    amp = values["radius_variation"]
    phase = math.tau * _stable_unit(branch_seed, 103)
    phase2 = math.tau * _stable_unit(branch_seed, 131)
    envelope = math.sin(math.pi * t) ** 0.72 if 0.0 < t < 1.0 else 0.0
    noise = 1.0 + amp * envelope * (
        0.62 * math.sin(phase + t * 7.2)
        + 0.38 * math.sin(phase2 + t * 15.7)
    )

    # One broad deterministic knuckle/swell breaks the mathematically perfect
    # radius curve without creating sharp rings in the mesh.
    knot_center = 0.20 + 0.52 * _stable_unit(branch_seed, 173)
    knot_width = 0.07 + 0.07 * _stable_unit(branch_seed, 191)
    knot_strength = amp * (0.30 + 0.55 * _stable_unit(branch_seed, 211))
    knot = 1.0 + knot_strength * math.exp(-((t - knot_center) / knot_width) ** 2)

    # Proximal swelling blends the attachment into its parent. branch_collar is
    # deliberately softened here because Exact Boolean handles the true union.
    swell_width = 0.11 + 0.04 * _stable_unit(branch_seed, 229)
    swell = 1.0 + values["base_swell"] * math.exp(-((t - 0.055) / swell_width) ** 2)
    collar_swell = 1.0 + collar * 0.42 * math.exp(-(t / 0.085) ** 2)

    radius = base_radius * core * noise * knot * swell * collar_swell

    # A child branch should never visually exceed the parent limb at its birth.
    if parent_radius > 0.0 and t < 0.16:
        cap = parent_radius * (0.93 if level <= 1 else 0.84)
        radius = min(radius, cap)

    return max(radius, base_radius * max(0.008, tip * 0.75))


def _apply_profiles(settings, branches, profile_settings):
    if not branches or not profile_settings.enabled:
        return branches

    values = effective_profile(settings, profile_settings)
    by_id = {int(branch.get("id", 0)): branch for branch in branches}
    ordered = sorted(branches, key=lambda branch: (int(branch.get("level", 0)), int(branch.get("id", 0))))

    for branch in ordered:
        level = int(branch.get("level", 0))
        if level <= 0:
            continue
        points = branch.get("points", ())
        if len(points) < 2:
            continue

        parent = by_id.get(int(branch.get("parent_id", -1)))
        if parent is None:
            continue

        parent_radius = _nearest_parent_radius(parent, points[0][0])
        lo, hi = _ratio_range(values, level)
        branch_id = int(branch.get("id", 0))
        ratio_u = _stable_unit(settings.seed ^ (level * 0x45D9F3B), branch_id * 97 + 13)
        ratio = lo + (hi - lo) * ratio_u

        # Slightly reduce the largest high-crown primary branches; low/mid limbs
        # tend to carry more mass in broadleaf trees.
        if level == 1:
            height_factor = max(0.0, min(1.0, points[0][0].z / max(settings.height, 1e-5)))
            ratio *= 1.0 - 0.12 * max(0.0, height_factor - 0.55) / 0.45

        base_radius = max(parent_radius * ratio, settings.base_radius * 0.010)
        collar = float(getattr(settings, "branch_collar", 0.0))
        branch_seed = settings.seed ^ (branch_id * 0x9E3779B1) ^ (level * 0x85EBCA6B)

        new_points = []
        count = len(points) - 1
        for index, (position, _old_radius) in enumerate(points):
            t = index / max(count, 1)
            radius = _radius_profile(
                t,
                base_radius,
                values,
                level,
                branch_seed,
                collar,
                parent_radius,
            )
            new_points.append((position.copy(), radius))

        branch["points"] = new_points
        branch["trees2_profile"] = values["resolved_name"]
        branch["trees2_profile_base_radius"] = base_radius
        branch["trees2_profile_parent_radius"] = parent_radius

    return branches


def _profiled_generate_skeleton(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    scene = getattr(bpy.context, "scene", None)
    profile_settings = getattr(scene, "trees2_branch_profile", None) if scene else None
    if profile_settings is None:
        return branches, terminals
    _apply_profiles(settings, branches, profile_settings)
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _profiled_generate_skeleton
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
