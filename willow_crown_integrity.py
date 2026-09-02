"""Quality-driven crown integrity for mature weeping willow.

The first scaffold-crown implementation guaranteed a *count* of major laterals,
but a generic short/high/central lateral could satisfy that count.  Some seeds
therefore still rendered as a long bare pole with foliage sheets hanging from a
thin upper web.

This deterministic WILLOW-only wrapper runs after ``willow_scaffold_crown`` and
before outward redistribution / structural motion.  It enforces visual rather
than nominal scaffold quality:

* only laterals with useful length and radial crown occupation count as majors;
* missing majors are created in the largest empty azimuth sectors;
* one low/early scaffold is guaranteed on detailed LODs so the crown does not
  begin as a narrow pole halfway up the tree;
* every accepted major scaffold carries several useful distal secondaries;
* all added branches use the existing structural metadata understood by the
  later pruning, hierarchy, junction and runtime-export stages;
* pendant-switch parent budgets are reduced so fine hanging wood supports the
  crown instead of overwhelming it with duplicate foliage curtains.
"""

import math
import random

from mathutils import Vector

from . import generator, willow_architecture, willow_pendant_switches


_PREVIOUS_GENERATE = None
_INSTALLED = False
_OLD_PARENT_LIMIT = None

_TARGET_QUALITY_SCAFFOLDS = {
    "LOD0": 4,
    "LOD1": 4,
    "LOD2": 3,
    "LOD3": 2,
    "LOD4": 1,
}

_TARGET_DISTAL_SECONDARIES = {
    "LOD0": 4,
    "LOD1": 3,
    "LOD2": 2,
    "LOD3": 1,
    "LOD4": 0,
}


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _new_id(branches):
    return max((int(branch.get("id", -1)) for branch in branches), default=-1) + 1


def _origin(branches):
    for branch in branches:
        if int(branch.get("level", 0)) == 0 and branch.get("points"):
            return branch["points"][0][0].copy()
    return Vector((0.0, 0.0, 0.0))


def _radial(point, origin):
    return math.hypot(float(point.x - origin.x), float(point.y - origin.y))


def _azimuth(point, origin):
    return math.atan2(float(point.y - origin.y), float(point.x - origin.x)) % math.tau


def _length(branch):
    return float(branch.get("length", generator._polyline_length(branch)))


def _outer_radius(branch, origin):
    if len(branch.get("points", ())) < 2:
        return 0.0
    values = []
    for factor in (0.48, 0.66, 0.82, 1.0):
        if factor >= 0.999:
            point = branch["points"][-1][0]
        else:
            point, _radius, _tangent = generator._point_on_polyline(branch, factor)
        values.append(_radial(point, origin))
    return max(values) if values else 0.0


def _crown_radius(branches, origin, settings):
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
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * 0.88))))
    return max(values[index], float(settings.base_radius) * 4.0, 1.0e-4)


def _children_map(branches):
    ids = {int(branch.get("id", -1)) for branch in branches}
    children = {}
    for branch in branches:
        parent_id = int(branch.get("parent_id", -1))
        if parent_id in ids:
            children.setdefault(parent_id, []).append(branch)
    return children


def _first_relay(branches, trunk):
    candidates = [
        branch for branch in branches
        if branch.get("willow_relay_axis", False)
        and int(branch.get("parent_id", -1)) == int(trunk.get("id", -1))
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda branch: int(branch.get("willow_relay_order", 1)))


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

    best_d = float("inf")
    best_l = 0.0
    for index in range(len(points) - 1):
        a = points[index][0]
        delta = points[index + 1][0] - a
        lsq = delta.length_squared
        if lsq <= 1.0e-12:
            continue
        local = _clamp((target - a).dot(delta) / lsq)
        projected = a + delta * local
        distance = (target - projected).length_squared
        if distance < best_d:
            best_d = distance
            best_l = cumulative[index] + math.sqrt(lsq) * local
    return _clamp(best_l / total)


def _world_to_local_azimuth(parent, factor, world_azimuth):
    _point, _radius, tangent = generator._point_on_polyline(parent, _clamp(factor))
    u, v = generator._basis(tangent)
    desired = Vector((math.cos(world_azimuth), math.sin(world_azimuth), 0.0))
    desired -= tangent * desired.dot(tangent)
    if desired.length_squared <= 1.0e-10:
        desired = u.copy()
    else:
        desired.normalize()
    return math.atan2(desired.dot(v), desired.dot(u))


def _largest_azimuth_gap(angles, rng):
    if not angles:
        return rng.uniform(0.0, math.tau)
    ordered = sorted(value % math.tau for value in angles)
    best_gap = -1.0
    best_mid = ordered[0]
    for index, value in enumerate(ordered):
        nxt = ordered[(index + 1) % len(ordered)]
        if index == len(ordered) - 1:
            nxt += math.tau
        gap = nxt - value
        if gap > best_gap:
            best_gap = gap
            best_mid = value + gap * 0.5
    return best_mid % math.tau


def _carrier_branch(branch, carrier_ids):
    return (
        not branch.get("dead", False)
        and not branch.get("willow_root_buttress", False)
        and not branch.get("willow_relay_axis", False)
        and int(branch.get("parent_id", -1)) in carrier_ids
        and int(branch.get("level", 0)) <= 2
        and len(branch.get("points", ())) >= 2
    )


def _quality_scaffolds(branches, trunk, relay, origin, crown_radius, settings):
    carrier_ids = {int(trunk.get("id", -1))}
    if relay is not None:
        carrier_ids.add(int(relay.get("id", -1)))

    height = max(float(settings.height), 1.0e-5)
    qualified = []
    for branch in branches:
        if not _carrier_branch(branch, carrier_ids):
            continue
        level = int(branch.get("level", 1))
        length_ratio = _length(branch) / height
        exposure = _outer_radius(branch, origin) / max(crown_radius, 1.0e-5)
        min_length = 0.18 if level <= 1 else 0.145
        min_exposure = 0.46 if level <= 1 else 0.42
        if length_ratio < min_length or exposure < min_exposure:
            continue
        score = exposure * 1.7 + min(0.35, length_ratio) * 2.2
        if branch.get("willow_crown_scaffold", False):
            score += 0.30
        if branch.get("willow_scaffold_fill", False):
            score += 0.18
        qualified.append((score, branch))
    qualified.sort(key=lambda item: item[0], reverse=True)
    return qualified


def _has_low_scaffold(qualified, relay, settings):
    if relay is None:
        return True
    height = max(float(settings.height), 1.0e-5)
    for _score, branch in qualified:
        if int(branch.get("parent_id", -1)) != int(relay.get("id", -1)):
            continue
        factor = _closest_factor(relay, branch["points"][0][0])
        root_height = float(branch["points"][0][0].z) / height
        if factor <= 0.28 or root_height <= 0.42:
            return True
    return False


def _add_quality_scaffold(settings, branches, parent, origin, world_azimuth, factor, next_id, rng):
    local_azimuth = _world_to_local_azimuth(parent, factor, world_azimuth)
    child = willow_architecture._make_lateral_branch(
        settings,
        parent,
        next_id,
        rng,
        level=max(1, min(2, int(parent.get("level", 0)) + 1)),
        factor=factor,
        azimuth=local_azimuth,
        length_ratio=rng.uniform(0.58, 0.74),
        radius_ratio=rng.uniform(0.38, 0.47),
        forward=rng.uniform(0.32, 0.47),
        outward=rng.uniform(0.90, 1.05),
        upward=rng.uniform(-0.02, 0.10),
        bend=float(settings.branch_bend) * rng.uniform(0.92, 1.10),
        droop=float(settings.branch_droop) * rng.uniform(0.44, 0.72),
        collar_scale=0.72,
        metadata={
            "willow_crown_scaffold": True,
            "willow_scaffold_fill": True,
            "willow_architecture_added": True,
            "willow_quality_scaffold": True,
        },
    )
    branches.append(child)
    return child


def _ensure_quality_scaffolds(settings, branches, trunk, relay, origin, crown_radius):
    target = int(_TARGET_QUALITY_SCAFFOLDS.get(str(settings.lod), 4))
    if target <= 0:
        return [], _new_id(branches)

    parent = relay if relay is not None else trunk
    qualified = _quality_scaffolds(branches, trunk, relay, origin, crown_radius, settings)
    rng = random.Random(int(settings.seed) ^ 0xC801C0DE)
    next_id = _new_id(branches)
    added = []
    angles = [
        _azimuth(branch["points"][-1][0], origin)
        for _score, branch in qualified
        if branch.get("points")
    ]

    # A mature willow needs at least one meaningful lower scaffold.  Add this
    # first so the remaining fills can distribute around the full crown.
    if str(settings.lod) in {"LOD0", "LOD1", "LOD2"} and not _has_low_scaffold(qualified, relay, settings):
        angle = _largest_azimuth_gap(angles, rng) + rng.uniform(-0.14, 0.14)
        factor = rng.uniform(0.10, 0.22) if relay is not None else rng.uniform(0.24, 0.34)
        child = _add_quality_scaffold(settings, branches, parent, origin, angle, factor, next_id, rng)
        next_id += 1
        added.append(child)
        angles.append(_azimuth(child["points"][-1][0], origin))
        qualified.append((10.0, child))

    while len(qualified) < target:
        angle = _largest_azimuth_gap(angles, rng) + rng.uniform(-0.15, 0.15)
        # Spread origins over a broad transition band, with an explicit bias
        # toward the lower/middle relay rather than the upper pole.
        factor = rng.uniform(0.18, 0.48) if relay is not None else rng.uniform(0.28, 0.52)
        child = _add_quality_scaffold(settings, branches, parent, origin, angle, factor, next_id, rng)
        next_id += 1
        added.append(child)
        angles.append(_azimuth(child["points"][-1][0], origin))
        qualified.append((9.0 - len(added) * 0.01, child))

    return added, next_id


def _largest_factor_gap(factors, lo=0.38, hi=0.92):
    values = [lo] + sorted(_clamp(value, lo, hi) for value in factors if lo < value < hi) + [hi]
    best_gap = -1.0
    best_mid = (lo + hi) * 0.5
    for a, b in zip(values[:-1], values[1:]):
        gap = b - a
        if gap > best_gap:
            best_gap = gap
            best_mid = (a + b) * 0.5
    return best_mid


def _ensure_distal_secondaries(settings, branches, majors, next_id, origin):
    target = int(_TARGET_DISTAL_SECONDARIES.get(str(settings.lod), 4))
    if target <= 0:
        return [], next_id

    rng = random.Random(int(settings.seed) ^ 0x5EC0A11D)
    children = _children_map(branches)
    added = []

    for _score, parent in majors:
        direct = [
            child for child in children.get(int(parent.get("id", -1)), ())
            if not child.get("dead", False)
            and not child.get("willow_root_buttress", False)
            and child.get("points")
        ]
        factors = [_closest_factor(parent, child["points"][0][0]) for child in direct]
        useful = [value for value in factors if value >= 0.36]
        need = max(0, target - len(useful))

        for _index in range(need):
            factor = _clamp(_largest_factor_gap(factors, 0.38, 0.93) + rng.uniform(-0.02, 0.02), 0.36, 0.95)
            start, _radius, tangent = generator._point_on_polyline(parent, factor)
            outward_world = _azimuth(start, origin)
            outward_world += rng.choice((-1.0, 1.0)) * rng.uniform(0.38, 0.92)
            local_azimuth = _world_to_local_azimuth(parent, factor, outward_world)
            child = willow_architecture._make_lateral_branch(
                settings,
                parent,
                next_id,
                rng,
                level=min(4, max(2, int(parent.get("level", 1)) + 1)),
                factor=factor,
                azimuth=local_azimuth,
                length_ratio=rng.uniform(0.34, 0.48),
                radius_ratio=rng.uniform(0.24, 0.33),
                forward=rng.uniform(0.26, 0.44),
                outward=rng.uniform(0.88, 1.06),
                upward=rng.uniform(-0.06, 0.05),
                bend=float(settings.branch_bend) * rng.uniform(1.02, 1.22),
                droop=float(settings.branch_droop) * rng.uniform(0.82, 1.16),
                collar_scale=0.58,
                metadata={
                    "willow_progressive_secondary": True,
                    "willow_structural_fork": True,
                    "willow_architecture_added": True,
                    "willow_quality_secondary": True,
                },
            )
            next_id += 1
            branches.append(child)
            added.append(child)
            factors.append(factor)

    return added, next_id


def _recompute_terminals(branches):
    living_ids = {int(branch.get("id", -1)) for branch in branches if not branch.get("dead", False)}
    parent_ids = {
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
        and int(branch.get("id", -1)) not in parent_ids
        and len(branch.get("points", ())) >= 2
    ]


def _generate_integrity(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    branches = list(branches)
    trunk = min(branches, key=lambda branch: (int(branch.get("level", 0)), int(branch.get("id", 0))))
    relay = _first_relay(branches, trunk)
    origin = _origin(branches)
    crown_radius = _crown_radius(branches, origin, settings)

    added_scaffolds, next_id = _ensure_quality_scaffolds(
        settings, branches, trunk, relay, origin, crown_radius
    )
    crown_radius = _crown_radius(branches, origin, settings)
    majors = _quality_scaffolds(branches, trunk, relay, origin, crown_radius, settings)
    target = int(_TARGET_QUALITY_SCAFFOLDS.get(str(settings.lod), 4))
    majors = majors[: max(1, target)]
    added_secondaries, next_id = _ensure_distal_secondaries(
        settings, branches, majors, next_id, origin
    )

    terminals = _recompute_terminals(branches)
    trunk["willow_crown_integrity_version"] = 1
    trunk["willow_quality_scaffolds_added"] = int(len(added_scaffolds))
    trunk["willow_quality_secondaries_added"] = int(len(added_secondaries))
    trunk["willow_quality_scaffold_count"] = int(len(majors))
    return branches, terminals


def prepare():
    """Reduce pendant parent budgets before the switch generator is executed."""
    global _OLD_PARENT_LIMIT
    if _OLD_PARENT_LIMIT is not None:
        return
    _OLD_PARENT_LIMIT = dict(willow_pendant_switches._PARENT_LIMIT)
    willow_pendant_switches._PARENT_LIMIT.update({
        "LOD0": 12,
        "LOD1": 9,
        "LOD2": 6,
        "LOD3": 3,
        "LOD4": 0,
    })


def restore_preparation():
    global _OLD_PARENT_LIMIT
    if _OLD_PARENT_LIMIT is None:
        return
    willow_pendant_switches._PARENT_LIMIT.clear()
    willow_pendant_switches._PARENT_LIMIT.update(_OLD_PARENT_LIMIT)
    _OLD_PARENT_LIMIT = None


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_integrity
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
