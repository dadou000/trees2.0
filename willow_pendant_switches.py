"""Generate real pendant switch branches for mature weeping willow.

A convincing willow crown is supported by many slender flexible shoots.  Hanging
leaf cards alone cannot provide that structure: they look like curtains floating
from sparse scaffold tips.  This post-structure pass adds a modest number of
actual thin woody switches from exposed secondary/tertiary branches after all
major branch motion/balancing is complete and before foliage-anchor scoring.

The switches are deterministic, outward-biased and progressively gravity-bent.
They are real branch records with IDs, so wood rendering, GPU branch mappings,
foliage bindings and game export all see the same support topology.
"""

import math
import random

from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False
_WORLD_DOWN = Vector((0.0, 0.0, -1.0))
_WORLD_UP = Vector((0.0, 0.0, 1.0))

_PARENT_LIMIT = {
    "LOD0": 20,
    "LOD1": 14,
    "LOD2": 8,
    "LOD3": 4,
    "LOD4": 0,
}

_SEGMENTS = {
    "LOD0": 9,
    "LOD1": 7,
    "LOD2": 5,
    "LOD3": 4,
    "LOD4": 3,
}


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _safe_normalized(vector, fallback):
    if vector.length_squared <= 1.0e-12:
        return fallback.copy()
    return vector.normalized()


def _new_id(branches):
    return max((int(branch.get("id", -1)) for branch in branches), default=-1) + 1


def _branch_length(branch):
    return float(branch.get("length", generator._polyline_length(branch)))


def _origin(branches):
    for branch in branches:
        if int(branch.get("level", 0)) == 0 and branch.get("points"):
            return branch["points"][0][0].copy()
    return Vector((0.0, 0.0, 0.0))


def _radial(point, origin):
    return math.hypot(float(point.x - origin.x), float(point.y - origin.y))


def _outer_radius(branch, origin):
    values = []
    for factor in (0.55, 0.72, 0.88, 1.0):
        if factor >= 0.999:
            point = branch["points"][-1][0]
        else:
            point, _radius, _tangent = generator._point_on_polyline(branch, factor)
        values.append(_radial(point, origin))
    return max(values) if values else 0.0


def _crown_reference(branches, origin, settings):
    values = []
    for branch in branches:
        if (
            branch.get("dead", False)
            or branch.get("willow_root_buttress", False)
            or int(branch.get("level", 0)) < 1
            or len(branch.get("points", ())) < 2
        ):
            continue
        values.append(_outer_radius(branch, origin))
    if not values:
        return max(float(settings.branch_length), float(settings.base_radius) * 4.0, 1.0)
    values.sort()
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * 0.90))))
    return max(values[index], float(settings.base_radius) * 4.0, 1.0)


def _children_map(branches):
    ids = {int(branch.get("id", -1)) for branch in branches}
    children = {}
    for branch in branches:
        parent_id = int(branch.get("parent_id", -1))
        if parent_id in ids:
            children.setdefault(parent_id, []).append(branch)
    return children


def _closest_factor(parent, target):
    points = parent.get("points", ())
    if len(points) < 2:
        return 0.0
    cumulative = [0.0]
    total = 0.0
    for index in range(len(points) - 1):
        total += (points[index + 1][0] - points[index][0]).length
        cumulative.append(total)
    if total <= 1.0e-9:
        return 0.0

    best_distance = float("inf")
    best_length = 0.0
    for index in range(len(points) - 1):
        a = points[index][0]
        delta = points[index + 1][0] - a
        length_sq = delta.length_squared
        if length_sq <= 1.0e-12:
            continue
        local = _clamp((target - a).dot(delta) / length_sq)
        projected = a + delta * local
        distance = (target - projected).length_squared
        if distance < best_distance:
            best_distance = distance
            best_length = cumulative[index] + math.sqrt(length_sq) * local
    return _clamp(best_length / total)


def _largest_gap(factors, lo=0.48, hi=0.96):
    values = [lo] + sorted(_clamp(value, lo, hi) for value in factors if lo < value < hi) + [hi]
    best_gap = -1.0
    best_mid = (lo + hi) * 0.5
    for a, b in zip(values[:-1], values[1:]):
        gap = b - a
        if gap > best_gap:
            best_gap = gap
            best_mid = (a + b) * 0.5
    return best_mid


def _parent_score(branch, origin, crown_radius, settings, direct_children):
    if (
        branch.get("dead", False)
        or branch.get("willow_no_foliage", False)
        or branch.get("willow_root_buttress", False)
        or branch.get("willow_relay_axis", False)
        or branch.get("willow_pendant_switch", False)
        or len(branch.get("points", ())) < 2
    ):
        return -1.0

    level = int(branch.get("level", 0))
    if level < 2 or level > 3:
        return -1.0

    exposure = _outer_radius(branch, origin) / max(crown_radius, 1.0e-5)
    if exposure < 0.42:
        return -1.0

    length_norm = _branch_length(branch) / max(float(settings.height), 1.0e-5)
    if length_norm < 0.045:
        return -1.0

    point = branch["points"][-1][0]
    h = _clamp(float(point.z) / max(float(settings.height), 1.0e-5))
    if h < 0.28:
        return -1.0

    structural = 0.18 if (
        branch.get("willow_structural_fork", False)
        or branch.get("willow_progressive_secondary", False)
        or branch.get("willow_relay_scaffold", False)
    ) else 0.0
    child_penalty = max(0, len(direct_children) - 3) * 0.12
    middle_band = 1.0 - abs(h - 0.64) / 0.64
    return exposure * 1.55 + min(0.28, length_norm) * 2.2 + middle_band * 0.28 + structural - child_penalty


def _switch_count(parent, exposure, settings):
    length = _branch_length(parent)
    base = 1
    if str(settings.lod) == "LOD0":
        if length > 1.6:
            base += 1
        if length > 2.7 and exposure > 0.62:
            base += 1
    elif str(settings.lod) == "LOD1":
        if length > 2.0 and exposure > 0.58:
            base += 1
    return min(3, base)


def _make_switch(settings, parent, branch_id, factor, rng, origin):
    start, parent_radius, tangent = generator._point_on_polyline(parent, factor)
    radial = Vector((start.x - origin.x, start.y - origin.y, 0.0))
    if radial.length_squared <= 1.0e-10:
        u, _v = generator._basis(tangent)
        radial = Vector((u.x, u.y, 0.0))
    radial = _safe_normalized(radial, Vector((1.0, 0.0, 0.0)))
    side = _safe_normalized(_WORLD_UP.cross(radial), Vector((0.0, 1.0, 0.0)))

    parent_length = max(_branch_length(parent), 0.25)
    height = max(float(settings.height), 1.0)
    length = parent_length * rng.uniform(0.30, 0.46)
    length = max(length, height * rng.uniform(0.060, 0.090))
    length = min(length, height * rng.uniform(0.115, 0.165))

    level = min(4, max(3, int(parent.get("level", 2)) + 1))
    root_radius = min(
        parent_radius * rng.uniform(0.13, 0.20),
        float(settings.base_radius) * rng.uniform(0.030, 0.046),
    )
    root_radius = max(root_radius, float(settings.base_radius) * 0.008)

    segments = max(4, int(_SEGMENTS.get(str(settings.lod), 7)))
    step = length / segments
    phase = rng.uniform(0.0, math.tau)
    side_sign = -1.0 if rng.random() < 0.5 else 1.0

    initial = _safe_normalized(
        tangent * rng.uniform(0.32, 0.48)
        + radial * rng.uniform(0.68, 0.88)
        + _WORLD_DOWN * rng.uniform(0.03, 0.10),
        radial,
    )
    direction = initial
    position = start.copy()
    points = []

    for index in range(segments + 1):
        t = index / segments
        radius = max(
            root_radius * ((1.0 - t) ** 1.22),
            root_radius * 0.035,
        )
        if index == 0:
            radius *= 1.0 + min(0.14, float(settings.branch_collar) * 0.28)
        points.append((position.copy(), radius))
        if index == segments:
            break

        # A switch starts outward/oblique, then its own weight dominates.  The
        # low-frequency side term prevents ruler-straight hanging wires.
        wave = math.sin(phase + t * math.pi * 1.7) * (0.045 + 0.035 * t)
        target = (
            initial * (0.72 - 0.34 * t)
            + radial * (0.24 + 0.10 * t)
            + _WORLD_DOWN * (0.12 + 0.70 * (t ** 1.45))
            + side * side_sign * wave
        )
        direction = _safe_normalized(direction * 0.58 + target * 0.42, direction)
        position += direction * step

    return {
        "id": int(branch_id),
        "level": int(level),
        "parent_id": int(parent.get("id", -1)),
        "points": points,
        "dead": False,
        "phase": rng.random(),
        "length": generator._polyline_length({"points": points}),
        "willow_pendant_switch": True,
        "willow_architecture_added": True,
        "willow_terminal_weight": 1.06,
        "willow_terminal_length_scale": 1.00,
        "willow_terminal_fill_only": False,
    }


def _recompute_terminals(branches):
    living_ids = {
        int(branch.get("id", -1))
        for branch in branches
        if not branch.get("dead", False)
    }
    parents = {
        int(branch.get("parent_id", -1))
        for branch in branches
        if not branch.get("dead", False)
        and int(branch.get("parent_id", -1)) in living_ids
    }
    return [
        branch for branch in branches
        if int(branch.get("level", 0)) > 0
        and not branch.get("dead", False)
        and not branch.get("willow_no_foliage", False)
        and not branch.get("willow_root_buttress", False)
        and int(branch.get("id", -1)) not in parents
        and len(branch.get("points", ())) >= 2
    ]


def _generate_switches(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    parent_limit = int(_PARENT_LIMIT.get(str(settings.lod), 0))
    if parent_limit <= 0:
        return branches, terminals

    branches = list(branches)
    origin = _origin(branches)
    crown_radius = _crown_reference(branches, origin, settings)
    children = _children_map(branches)

    ranked = []
    for branch in branches:
        direct = children.get(int(branch.get("id", -1)), ())
        score = _parent_score(branch, origin, crown_radius, settings, direct)
        if score >= 0.0:
            ranked.append((score, branch))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [branch for _score, branch in ranked[:parent_limit]]

    next_id = _new_id(branches)
    added = []
    for parent in selected:
        parent_id = int(parent.get("id", -1))
        direct = children.get(parent_id, ())
        factors = [
            _closest_factor(parent, child["points"][0][0])
            for child in direct
            if child.get("points")
        ]
        exposure = _outer_radius(parent, origin) / max(crown_radius, 1.0e-5)
        count = _switch_count(parent, exposure, settings)
        rng = random.Random(int(settings.seed) ^ (parent_id * 0x1F123BB5) ^ 0x5A17C4)

        for local_index in range(count):
            factor = _largest_gap(factors, 0.48, 0.96)
            factor += rng.uniform(-0.018, 0.018)
            factor = _clamp(factor, 0.46, 0.97)
            switch = _make_switch(settings, parent, next_id, factor, rng, origin)
            next_id += 1
            branches.append(switch)
            added.append(switch)
            factors.append(factor)

    terminals = _recompute_terminals(branches)
    try:
        trunk = next(branch for branch in branches if int(branch.get("level", 0)) == 0)
        trunk["willow_pendant_switch_version"] = 1
        trunk["willow_pendant_switch_parents"] = int(len(selected))
        trunk["willow_pendant_switch_count"] = int(len(added))
    except Exception:
        pass
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_switches
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
