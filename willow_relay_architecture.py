"""Research-driven sympodial relay architecture for mature weeping willow.

Salix architecture is sympodial rather than a permanent straight terminal pole:
a vigorous distal shoot can take over height while lateral shoots become strongly
pendulous. This module keeps a short basal trunk, terminates that original axis,
and continues the crown through successive obliquely upright relay shoots.

Unlike the earlier forced multi-leader experiment, existing generic crown
subtrees are not discarded. Whole subtrees that originally attached above the
new trunk termination are rigidly transferred onto the relay axes, preserving
branch count, local topology and foliage density while changing the supporting
architecture.
"""

import math
import random

from . import generator, willow_architecture


_PREVIOUS_GENERATE = None
_INSTALLED = False
_PREPARED = False
_OLD_ARCHITECTURE = {}


_RELAY_LOD = {
    "LOD0": dict(relays=2, first_scaffolds=3, second_scaffolds=3, daughter_chance=0.68),
    "LOD1": dict(relays=2, first_scaffolds=3, second_scaffolds=2, daughter_chance=0.54),
    "LOD2": dict(relays=1, first_scaffolds=2, second_scaffolds=0, daughter_chance=0.34),
    "LOD3": dict(relays=1, first_scaffolds=1, second_scaffolds=0, daughter_chance=0.0),
    "LOD4": dict(relays=0, first_scaffolds=0, second_scaffolds=0, daughter_chance=0.0),
}


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _new_id(branches):
    return max((int(branch.get("id", -1)) for branch in branches), default=-1) + 1


def _polyline_cumulative(points):
    cumulative = [0.0]
    total = 0.0
    for index in range(len(points) - 1):
        total += (points[index + 1][0] - points[index][0]).length
        cumulative.append(total)
    return cumulative, total


def _closest_factor(branch, target):
    points = branch.get("points", ())
    if len(points) < 2:
        return 0.0
    cumulative, total = _polyline_cumulative(points)
    if total <= 1.0e-8:
        return 0.0

    best_distance = float("inf")
    best_length = 0.0
    for index in range(len(points) - 1):
        a = points[index][0]
        delta = points[index + 1][0] - a
        length_sq = delta.length_squared
        if length_sq <= 1.0e-12:
            local = 0.0
            projection = a
        else:
            local = _clamp((target - a).dot(delta) / length_sq)
            projection = a + delta * local
        distance = (target - projection).length_squared
        if distance < best_distance:
            best_distance = distance
            best_length = cumulative[index] + math.sqrt(max(length_sq, 0.0)) * local
    return _clamp(best_length / total)


def _truncate_branch(branch, factor, minimum_tip_radius):
    """Trim at an exact arc-length factor and fair the aborted parent-shoot stub."""
    points = branch.get("points", ())
    if len(points) < 2:
        return
    factor = _clamp(factor, 0.05, 0.98)
    cumulative, total = _polyline_cumulative(points)
    if total <= 1.0e-8:
        return
    target = total * factor

    output = []
    for index, (point, radius) in enumerate(points):
        distance = cumulative[index]
        if distance < target:
            output.append((point.copy(), float(radius)))
            continue
        if abs(distance - target) <= 1.0e-8:
            output.append((point.copy(), float(radius)))
        elif index > 0:
            previous_distance = cumulative[index - 1]
            span = max(distance - previous_distance, 1.0e-8)
            local = _clamp((target - previous_distance) / span)
            a_point, a_radius = points[index - 1]
            b_point, b_radius = points[index]
            p = a_point.lerp(b_point, local)
            r = float(a_radius) + (float(b_radius) - float(a_radius)) * local
            output.append((p, r))
        break

    if len(output) < 2:
        output = [(p.copy(), float(r)) for p, r in points[:2]]

    start_index = max(1, int(round((len(output) - 1) * 0.80)))
    start_radius = float(output[start_index][1])
    denominator = max(1, len(output) - 1 - start_index)
    for index in range(start_index, len(output)):
        t = (index - start_index) / denominator
        radius = max(float(minimum_tip_radius), start_radius * (1.0 - 0.72 * t))
        output[index] = (output[index][0], radius)

    branch["points"] = output
    branch["length"] = generator._polyline_length(branch)
    branch["willow_relay_parent_stub"] = True


def _children_map(branches):
    children = {}
    for branch in branches:
        children.setdefault(int(branch.get("parent_id", -1)), []).append(branch)
    return children


def _subtree(root, children):
    result = []
    stack = [root]
    seen = set()
    while stack:
        branch = stack.pop()
        branch_id = int(branch.get("id", -1))
        if branch_id in seen:
            continue
        seen.add(branch_id)
        result.append(branch)
        stack.extend(children.get(branch_id, ()))
    return result


def _upper_side_azimuth(parent, factor, rng):
    """Prefer the upper side of an already-curved parent for an axis takeover."""
    _point, _radius, tangent = generator._point_on_polyline(parent, factor)
    u, v = generator._basis(tangent)
    energy = abs(float(u.z)) + abs(float(v.z))
    if energy < 0.08:
        return rng.uniform(0.0, math.tau)
    return math.atan2(float(v.z), float(u.z)) + rng.uniform(-0.22, 0.22)


def _make_relay(settings, parent, branch_id, rng, factor, *, second=False):
    if second:
        length_ratio = rng.uniform(0.52, 0.64)
        radius_ratio = rng.uniform(0.78, 0.91)
        forward = rng.uniform(0.76, 0.88)
        outward = rng.uniform(0.18, 0.31)
        upward = rng.uniform(0.24, 0.38)
        bend = float(settings.branch_bend) * rng.uniform(0.56, 0.76)
    else:
        length_ratio = rng.uniform(0.56, 0.66)
        radius_ratio = rng.uniform(0.72, 0.82)
        forward = rng.uniform(0.68, 0.80)
        outward = rng.uniform(0.30, 0.43)
        upward = rng.uniform(0.27, 0.41)
        bend = float(settings.branch_bend) * rng.uniform(0.60, 0.82)

    return willow_architecture._make_lateral_branch(
        settings,
        parent,
        branch_id,
        rng,
        level=1,
        factor=factor,
        azimuth=_upper_side_azimuth(parent, factor, rng),
        length_ratio=length_ratio,
        radius_ratio=radius_ratio,
        forward=forward,
        outward=outward,
        upward=upward,
        bend=bend,
        droop=float(settings.branch_droop) * rng.uniform(0.08, 0.20),
        collar_scale=1.22,
        metadata={
            "willow_relay_axis": True,
            "willow_architecture_added": True,
            "willow_no_foliage": True,
            "willow_relay_order": 2 if second else 1,
        },
    )


def _add_relay_scaffolds(settings, branches, parent, next_id, rng, count, daughter_chance):
    if count <= 0:
        return next_id
    phase = rng.uniform(0.0, math.tau)
    for index in range(count):
        factor = _clamp(
            0.28 + (index + rng.uniform(0.22, 0.78)) / max(count, 1) * 0.58,
            0.28,
            0.88,
        )
        azimuth = phase + index * (math.tau / max(count + 1, 3)) + rng.uniform(-0.48, 0.48)
        child = willow_architecture._make_lateral_branch(
            settings,
            parent,
            next_id,
            rng,
            level=2,
            factor=factor,
            azimuth=azimuth,
            length_ratio=rng.uniform(0.35, 0.49),
            radius_ratio=rng.uniform(0.34, 0.44),
            forward=rng.uniform(0.34, 0.52),
            outward=rng.uniform(0.72, 0.92),
            upward=rng.uniform(0.05, 0.17),
            bend=float(settings.branch_bend) * rng.uniform(0.78, 1.00),
            droop=float(settings.branch_droop) * rng.uniform(0.48, 0.76),
            collar_scale=0.86,
            metadata={"willow_relay_scaffold": True, "willow_architecture_added": True},
        )
        next_id += 1
        branches.append(child)

        if rng.random() < float(daughter_chance):
            daughter = willow_architecture._make_lateral_branch(
                settings,
                child,
                next_id,
                rng,
                level=3,
                factor=rng.uniform(0.46, 0.78),
                azimuth=azimuth + rng.choice((-1.0, 1.0)) * rng.uniform(0.62, 1.28),
                length_ratio=rng.uniform(0.39, 0.53),
                radius_ratio=rng.uniform(0.30, 0.39),
                forward=rng.uniform(0.24, 0.43),
                outward=rng.uniform(0.79, 1.00),
                upward=rng.uniform(-0.10, 0.03),
                bend=float(settings.branch_bend) * rng.uniform(0.96, 1.18),
                droop=float(settings.branch_droop) * rng.uniform(1.02, 1.28),
                collar_scale=0.72,
                metadata={"willow_relay_scaffold": True, "willow_architecture_added": True},
            )
            next_id += 1
            branches.append(daughter)
    return next_id


def _transform_subtree(subtree, old_origin, new_origin, rotation, level_delta=1):
    for branch in subtree:
        transformed = []
        for point, radius in branch.get("points", ()):
            transformed.append((new_origin + rotation @ (point - old_origin), float(radius)))
        if transformed:
            branch["points"] = transformed
            branch["length"] = generator._polyline_length(branch)
        branch["level"] = min(4, max(1, int(branch.get("level", 1)) + level_delta))
        branch["willow_relay_reparented"] = True


def _transfer_upper_subtrees(branches, trunk, cutoff_factor, relay_axes):
    """Move complete former upper-trunk subtrees onto the new relay chain."""
    if not relay_axes:
        return 0
    children = _children_map(branches)
    trunk_id = int(trunk.get("id", 0))
    protected = {int(branch.get("id", -1)) for branch in relay_axes}
    candidates = []

    for root in children.get(trunk_id, ()):
        root_id = int(root.get("id", -1))
        if root_id in protected or root.get("willow_root_buttress", False):
            continue
        points = root.get("points", ())
        if not points:
            continue
        factor = _closest_factor(trunk, points[0][0])
        if factor > cutoff_factor:
            candidates.append((factor, root))

    candidates.sort(key=lambda item: item[0])
    transferred = 0
    for factor, root in candidates:
        q = _clamp((factor - cutoff_factor) / max(1.0 - cutoff_factor, 1.0e-5))
        if len(relay_axes) >= 2 and q >= 0.47:
            parent = relay_axes[1]
            local_q = _clamp((q - 0.47) / 0.53)
            target_factor = 0.26 + 0.62 * local_q
        else:
            parent = relay_axes[0]
            local_q = _clamp(q / 0.47) if len(relay_axes) >= 2 else q
            target_factor = 0.28 + 0.58 * local_q

        old_origin, _old_radius, old_tangent = generator._point_on_polyline(trunk, factor)
        new_origin, _new_radius, new_tangent = generator._point_on_polyline(parent, _clamp(target_factor, 0.24, 0.90))
        try:
            rotation = old_tangent.rotation_difference(new_tangent)
        except Exception:
            rotation = None
        if rotation is None:
            continue

        subtree = _subtree(root, children)
        _transform_subtree(subtree, old_origin, new_origin, rotation, level_delta=1)
        root["parent_id"] = int(parent.get("id", -1))
        root["willow_relay_attachment_factor"] = float(target_factor)
        transferred += len(subtree)

    return transferred


def _recompute_terminals(branches):
    living_ids = {int(branch.get("id", -1)) for branch in branches if not branch.get("dead", False)}
    parents_with_living_children = {
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
        and int(branch.get("id", -1)) not in parents_with_living_children
        and len(branch.get("points", ())) >= 2
    ]


def _generate_relay_willow(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    cfg = _RELAY_LOD.get(str(settings.lod), _RELAY_LOD["LOD0"])
    relay_count = int(cfg["relays"])
    if relay_count <= 0:
        return branches, terminals

    branches = list(branches)
    trunk = branches[0]
    rng = random.Random(int(settings.seed) ^ 0x5A11C0DE)
    next_id = _new_id(branches)

    first_factor = rng.uniform(0.265, 0.325)
    first_relay = _make_relay(settings, trunk, next_id, rng, first_factor, second=False)
    next_id += 1
    branches.append(first_relay)
    next_id = _add_relay_scaffolds(
        settings, branches, first_relay, next_id, rng,
        int(cfg["first_scaffolds"]), float(cfg["daughter_chance"]),
    )

    relay_axes = [first_relay]
    if relay_count >= 2:
        second_factor = rng.uniform(0.54, 0.66)
        second_relay = _make_relay(settings, first_relay, next_id, rng, second_factor, second=True)
        next_id += 1
        branches.append(second_relay)
        relay_axes.append(second_relay)
        next_id = _add_relay_scaffolds(
            settings, branches, second_relay, next_id, rng,
            int(cfg["second_scaffolds"]), float(cfg["daughter_chance"]) * 0.86,
        )

    trunk_cutoff = min(0.42, first_factor + rng.uniform(0.050, 0.070))
    transferred = _transfer_upper_subtrees(branches, trunk, trunk_cutoff, relay_axes)
    _truncate_branch(
        trunk,
        trunk_cutoff,
        minimum_tip_radius=max(float(settings.base_radius) * 0.020, 0.006),
    )

    terminals = _recompute_terminals(branches)
    trunk["willow_relay_architecture_version"] = 2
    trunk["willow_first_relay_fraction"] = float(first_factor)
    trunk["willow_trunk_cutoff_fraction"] = float(trunk_cutoff)
    trunk["willow_trunk_terminated"] = True
    trunk["willow_relay_count"] = len(relay_axes)
    trunk["willow_transferred_branch_records"] = int(transferred)
    return branches, terminals


def prepare():
    """Disable the older forced equal co-dominant leaders before architecture installs."""
    global _PREPARED
    if _PREPARED:
        return
    _OLD_ARCHITECTURE.clear()
    for lod, cfg in willow_architecture._LOD_ARCHITECTURE.items():
        _OLD_ARCHITECTURE[lod] = dict(cfg)
        cfg["leaders"] = 0
    _PREPARED = True


def restore_preparation():
    global _PREPARED
    if not _PREPARED:
        return
    for lod, old in _OLD_ARCHITECTURE.items():
        if lod in willow_architecture._LOD_ARCHITECTURE:
            willow_architecture._LOD_ARCHITECTURE[lod].clear()
            willow_architecture._LOD_ARCHITECTURE[lod].update(old)
    _OLD_ARCHITECTURE.clear()
    _PREPARED = False


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_relay_willow
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
