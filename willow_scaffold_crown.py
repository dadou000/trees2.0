"""Coherent scaffold-crown architecture for mature weeping willow.

This pass runs after the sympodial relay hand-off and before the existing
outward-distribution / motion stages.  It corrects the remaining visual failure
where the tree reads as one central pole with a few isolated arms and a dense
upper-core twig web.

For WILLOW only it:
* guarantees a small 3-5 member major scaffold set (LOD dependent);
* fills missing azimuth sectors instead of adding another radial whorl;
* distributes new scaffold roots over a short band on the first relay;
* fills long empty distal spans on major scaffolds with real secondaries;
* removes only deterministic generic fine-branch subtrees from the upper inner
  core, while protecting explicit relay/scaffold/structural branches;
* keeps branch IDs deterministic and rebuilds the terminal list afterward.

The later outward, structural-motion, sinuosity and hierarchy passes still do
all final shaping and dimensional normalization.
"""

import math
import random

from mathutils import Vector

from . import generator, willow_architecture


_PREVIOUS_GENERATE = None
_INSTALLED = False

_WORLD_UP = Vector((0.0, 0.0, 1.0))

_TARGET_SCAFFOLDS = {
    "LOD0": 4,
    "LOD1": 4,
    "LOD2": 3,
    "LOD3": 2,
    "LOD4": 1,
}

_TARGET_SECONDARIES = {
    "LOD0": 3,
    "LOD1": 3,
    "LOD2": 2,
    "LOD3": 1,
    "LOD4": 0,
}


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _stable_unit(seed, value, salt=0):
    x = (int(seed) ^ (int(value) * 0x9E3779B1) ^ int(salt)) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def _new_id(branches):
    return max((int(branch.get("id", -1)) for branch in branches), default=-1) + 1


def _branch_length(branch):
    return float(branch.get("length", generator._polyline_length(branch)))


def _children_map(branches):
    ids = {int(branch.get("id", -1)) for branch in branches}
    children = {}
    for branch in branches:
        parent_id = int(branch.get("parent_id", -1))
        if parent_id in ids:
            children.setdefault(parent_id, []).append(branch)
    return children


def _subtree_ids(root, children):
    result = set()
    stack = [root]
    while stack:
        branch = stack.pop()
        branch_id = int(branch.get("id", -1))
        if branch_id in result:
            continue
        result.add(branch_id)
        stack.extend(children.get(branch_id, ()))
    return result


def _origin(branches):
    for branch in branches:
        if int(branch.get("level", 0)) == 0 and branch.get("points"):
            return branch["points"][0][0].copy()
    for branch in branches:
        if branch.get("points"):
            return branch["points"][0][0].copy()
    return Vector((0.0, 0.0, 0.0))


def _radial(point, origin):
    return math.hypot(float(point.x - origin.x), float(point.y - origin.y))


def _azimuth(point, origin):
    return math.atan2(float(point.y - origin.y), float(point.x - origin.x)) % math.tau


def _sample_outer_radius(branch, origin):
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
        values.append(_sample_outer_radius(branch, origin))
    if not values:
        return max(float(settings.branch_length), float(settings.base_radius) * 4.0, 1.0)
    values.sort()
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * 0.88))))
    return max(values[index], float(settings.base_radius) * 4.0, 1.0)


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


def _explicit_structure(branch):
    return bool(
        branch.get("willow_relay_axis", False)
        or branch.get("willow_relay_scaffold", False)
        or branch.get("willow_structural_fork", False)
        or branch.get("willow_scaffold_fill", False)
        or branch.get("willow_crown_scaffold", False)
        or branch.get("willow_progressive_secondary", False)
        or branch.get("willow_root_buttress", False)
    )


def _first_relay(branches, trunk):
    candidates = [
        branch for branch in branches
        if branch.get("willow_relay_axis", False)
        and int(branch.get("parent_id", -1)) == int(trunk.get("id", -1))
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda branch: int(branch.get("willow_relay_order", 1)))


def _major_candidates(branches, trunk, relay, origin, crown_radius):
    carrier_ids = {int(trunk.get("id", -1))}
    if relay is not None:
        carrier_ids.add(int(relay.get("id", -1)))

    result = []
    for branch in branches:
        if (
            branch.get("dead", False)
            or branch.get("willow_root_buttress", False)
            or branch.get("willow_relay_axis", False)
            or len(branch.get("points", ())) < 2
        ):
            continue
        level = int(branch.get("level", 0))
        parent_id = int(branch.get("parent_id", -1))
        if level > 2 or parent_id not in carrier_ids:
            continue

        exposure = _sample_outer_radius(branch, origin) / max(crown_radius, 1.0e-5)
        length_norm = _branch_length(branch) / max(float(crown_radius), 1.0e-5)
        root_radius = float(branch["points"][0][1])
        score = exposure * 1.55 + min(1.5, length_norm) * 0.72 + root_radius * 0.28
        if _explicit_structure(branch):
            score += 0.34
        result.append((score, branch))

    result.sort(key=lambda item: item[0], reverse=True)
    return result


def _largest_gap(angles, seed):
    if not angles:
        return _stable_unit(seed, 0x5311, 0x91) * math.tau
    ordered = sorted(angle % math.tau for angle in angles)
    best_gap = -1.0
    best_mid = ordered[0]
    for index, angle in enumerate(ordered):
        next_angle = ordered[(index + 1) % len(ordered)]
        if index == len(ordered) - 1:
            next_angle += math.tau
        gap = next_angle - angle
        if gap > best_gap:
            best_gap = gap
            best_mid = angle + gap * 0.5
    return best_mid % math.tau


def _world_azimuth_to_parent_azimuth(parent, factor, world_azimuth):
    _point, _radius, tangent = generator._point_on_polyline(parent, _clamp(factor))
    u, v = generator._basis(tangent)
    desired = Vector((math.cos(world_azimuth), math.sin(world_azimuth), 0.0))
    # Remove the tangent component so the requested azimuth remains a valid
    # direction in the branch's local normal plane.
    desired = desired - tangent * desired.dot(tangent)
    if desired.length_squared <= 1.0e-10:
        desired = u
    else:
        desired.normalize()
    return math.atan2(desired.dot(v), desired.dot(u))


def _add_missing_scaffolds(settings, branches, major, trunk, relay, origin):
    target = int(_TARGET_SCAFFOLDS.get(str(settings.lod), 4))
    if target <= 0:
        return [], _new_id(branches)

    # Keep one extra naturally strong scaffold in unusual seeds, but only add
    # until the nominal target is reached.
    existing = [branch for _score, branch in major[: max(target + 1, target)]]
    if len(existing) >= target:
        return [], _new_id(branches)

    parent = relay if relay is not None else trunk
    rng = random.Random(int(settings.seed) ^ 0x5CAFF01D)
    next_id = _new_id(branches)
    added = []
    endpoint_angles = [
        _azimuth(branch["points"][-1][0], origin)
        for branch in existing
        if branch.get("points")
    ]

    missing = target - len(existing)
    for slot in range(missing):
        world_az = _largest_gap(endpoint_angles, int(settings.seed) + slot * 97)
        world_az += rng.uniform(-0.16, 0.16)

        # Stagger major origins over a real crown-transition band instead of
        # creating a single hub/whorl at one ring.
        if missing <= 1:
            factor = rng.uniform(0.32, 0.48)
        else:
            t = (slot + 0.5) / missing
            factor = 0.24 + 0.38 * t + rng.uniform(-0.035, 0.035)
        factor = _clamp(factor, 0.22, 0.68)
        local_az = _world_azimuth_to_parent_azimuth(parent, factor, world_az)

        child = willow_architecture._make_lateral_branch(
            settings,
            parent,
            next_id,
            rng,
            level=max(1, min(2, int(parent.get("level", 0)) + 1)),
            factor=factor,
            azimuth=local_az,
            length_ratio=rng.uniform(0.54, 0.72),
            radius_ratio=rng.uniform(0.44, 0.54),
            forward=rng.uniform(0.34, 0.52),
            outward=rng.uniform(0.82, 1.02),
            upward=rng.uniform(0.02, 0.16),
            bend=float(settings.branch_bend) * rng.uniform(0.82, 1.02),
            droop=float(settings.branch_droop) * rng.uniform(0.36, 0.62),
            collar_scale=0.82,
            metadata={
                "willow_crown_scaffold": True,
                "willow_scaffold_fill": True,
                "willow_architecture_added": True,
            },
        )
        next_id += 1
        branches.append(child)
        added.append(child)
        endpoint_angles.append(_azimuth(child["points"][-1][0], origin))

    return added, next_id


def _largest_factor_gap(factors, lo=0.40, hi=0.90):
    values = [lo] + sorted(_clamp(value, lo, hi) for value in factors if lo < value < hi) + [hi]
    best_gap = -1.0
    best_mid = (lo + hi) * 0.5
    for a, b in zip(values[:-1], values[1:]):
        gap = b - a
        if gap > best_gap:
            best_gap = gap
            best_mid = (a + b) * 0.5
    return best_mid


def _add_progressive_secondaries(settings, branches, major_branches, next_id, origin):
    target = int(_TARGET_SECONDARIES.get(str(settings.lod), 3))
    if target <= 0:
        return [], next_id

    rng = random.Random(int(settings.seed) ^ 0x5EC0DA12)
    children = _children_map(branches)
    added = []

    for parent in major_branches:
        parent_id = int(parent.get("id", -1))
        if parent.get("willow_root_buttress", False) or len(parent.get("points", ())) < 2:
            continue

        direct = [
            child for child in children.get(parent_id, ())
            if not child.get("dead", False)
            and not child.get("willow_root_buttress", False)
            and int(child.get("level", 0)) <= 3
        ]
        factors = [
            _closest_factor(parent, child["points"][0][0])
            for child in direct
            if child.get("points")
        ]
        useful = sum(1 for value in factors if value >= 0.38)
        need = max(0, target - useful)

        for local_index in range(need):
            factor = _largest_factor_gap(factors, 0.40, 0.92)
            factor += rng.uniform(-0.025, 0.025)
            factor = _clamp(factor, 0.38, 0.94)
            start, _parent_radius, tangent = generator._point_on_polyline(parent, factor)
            world_az = _azimuth(start, origin)
            # Fan around the outward hemisphere rather than pointing children
            # back through the crown core.
            world_az += rng.choice((-1.0, 1.0)) * rng.uniform(0.38, 1.02)
            local_az = _world_azimuth_to_parent_azimuth(parent, factor, world_az)
            level = min(4, max(2, int(parent.get("level", 1)) + 1))

            child = willow_architecture._make_lateral_branch(
                settings,
                parent,
                next_id,
                rng,
                level=level,
                factor=factor,
                azimuth=local_az,
                length_ratio=rng.uniform(0.34, 0.49),
                radius_ratio=rng.uniform(0.27, 0.37),
                forward=rng.uniform(0.30, 0.48),
                outward=rng.uniform(0.84, 1.04),
                upward=rng.uniform(-0.04, 0.08),
                bend=float(settings.branch_bend) * rng.uniform(0.96, 1.18),
                droop=float(settings.branch_droop) * rng.uniform(0.72, 1.06),
                collar_scale=0.68,
                metadata={
                    "willow_progressive_secondary": True,
                    "willow_structural_fork": True,
                    "willow_architecture_added": True,
                },
            )
            next_id += 1
            branches.append(child)
            added.append(child)
            factors.append(factor)

    return added, next_id


def _prune_upper_core_web(settings, branches, origin, crown_radius):
    """Remove only generic fine subtrees responsible for the top-core spiderweb."""
    if str(settings.lod) not in {"LOD0", "LOD1", "LOD2"}:
        return branches, 0

    children = _children_map(branches)
    prune_roots = []
    height = max(float(settings.height), 1.0e-5)

    for branch in branches:
        level = int(branch.get("level", 0))
        if level < 3 or _explicit_structure(branch) or branch.get("dead", False):
            continue
        if len(branch.get("points", ())) < 2:
            continue

        outer = _sample_outer_radius(branch, origin) / max(crown_radius, 1.0e-5)
        end = branch["points"][-1][0]
        h = _clamp(float(end.z) / height)
        start = branch["points"][0][0]
        radial_gain = (
            _radial(end, origin) - _radial(start, origin)
        ) / max(crown_radius, 1.0e-5)

        # Strongest rejection is the high, inward-facing fine web.  Keep enough
        # random survivors for natural internal depth rather than hollowing the
        # crown into a shell.
        if h < 0.46 or outer >= 0.42:
            continue
        severity = _clamp((0.42 - outer) / 0.28) * 0.62
        if radial_gain < 0.02:
            severity += 0.18
        probability = _clamp(0.28 + severity, 0.28, 0.78)
        branch_id = int(branch.get("id", -1))
        if _stable_unit(int(settings.seed), branch_id, 0xC0A3) < probability:
            prune_roots.append(branch)

    if not prune_roots:
        return branches, 0

    remove_ids = set()
    for root in prune_roots:
        if int(root.get("id", -1)) in remove_ids:
            continue
        remove_ids.update(_subtree_ids(root, children))

    filtered = [branch for branch in branches if int(branch.get("id", -1)) not in remove_ids]
    return filtered, len(remove_ids)


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


def _generate_scaffold_crown(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    branches = list(branches)
    trunk = min(branches, key=lambda branch: (int(branch.get("level", 0)), int(branch.get("id", 0))))
    relay = _first_relay(branches, trunk)
    origin = _origin(branches)
    crown_radius = _crown_reference(branches, origin, settings)

    # First reduce the generic high-core web so added architecture fills useful
    # crown space instead of merely increasing branch count.
    branches, pruned = _prune_upper_core_web(settings, branches, origin, crown_radius)
    trunk = next((branch for branch in branches if int(branch.get("id", -1)) == int(trunk.get("id", -1))), trunk)
    relay = _first_relay(branches, trunk)

    major = _major_candidates(branches, trunk, relay, origin, crown_radius)
    added_scaffolds, next_id = _add_missing_scaffolds(settings, branches, major, trunk, relay, origin)

    # Re-score after additions and only propagate secondaries on the dominant
    # subset, preventing every minor branch from becoming another mini-tree.
    crown_radius = _crown_reference(branches, origin, settings)
    major = _major_candidates(branches, trunk, relay, origin, crown_radius)
    target = int(_TARGET_SCAFFOLDS.get(str(settings.lod), 4))
    dominant = [branch for _score, branch in major[: max(1, target)]]
    added_secondaries, next_id = _add_progressive_secondaries(
        settings, branches, dominant, next_id, origin
    )

    terminals = _recompute_terminals(branches)
    try:
        trunk["willow_scaffold_crown_version"] = 1
        trunk["willow_scaffold_target"] = int(target)
        trunk["willow_scaffold_added"] = int(len(added_scaffolds))
        trunk["willow_progressive_secondaries_added"] = int(len(added_secondaries))
        trunk["willow_upper_core_pruned"] = int(pruned)
    except Exception:
        pass
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_scaffold_crown
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
