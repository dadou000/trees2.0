"""Research-driven sympodial relay architecture for mature weeping willow.

Willows do not maintain a conventional monopodial terminal leader indefinitely.
Salix architecture is sympodial: vigorous distal/upper shoots can take over the
main axis while lateral shoots become progressively pendulous.  This module
models that behavior for WILLOW instead of forcing several equal low trunks.

Pipeline intent:
* keep a short, stout basal trunk and buttress roots,
* terminate the generic trunk shortly beyond a first relay point,
* continue height through one obliquely upright relay axis,
* optionally continue again through a distal second relay,
* grow real structural laterals from the relay axes,
* let the existing willow motion/foliage systems make those laterals pendulous.

The relay axes are deliberately level-1 branch records even when a relay is the
child of another relay.  That keeps their heavy-axis structural-motion profile,
while parent_id preserves the true hierarchy and exact junction relationship.
"""

import math
import random

from mathutils import Vector

from . import generator, willow_architecture


_PREVIOUS_GENERATE = None
_INSTALLED = False
_PREPARED = False
_OLD_ARCHITECTURE = {}

_WORLD_UP = Vector((0.0, 0.0, 1.0))


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
    """Trim a polyline at an exact arc-length factor and taper its short dead stub."""
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

    # The parent shoot biologically aborts rather than turning into a blunt pole.
    # Fair the last ~18% of the retained piece down into a subordinate terminal stub.
    start_index = max(1, int(round((len(output) - 1) * 0.82)))
    start_radius = float(output[start_index][1])
    count = max(1, len(output) - 1 - start_index)
    for index in range(start_index, len(output)):
        t = (index - start_index) / count
        radius = start_radius * (1.0 - 0.72 * t)
        radius = max(float(minimum_tip_radius), radius)
        output[index] = (output[index][0], radius)

    branch["points"] = output
    branch["length"] = generator._polyline_length(branch)
    branch["willow_relay_parent_stub"] = True


def _children_map(branches):
    children = {}
    for branch in branches:
        children.setdefault(int(branch.get("parent_id", -1)), []).append(branch)
    return children


def _descendant_ids(children, root_ids):
    remove = set(int(value) for value in root_ids)
    stack = list(remove)
    while stack:
        branch_id = stack.pop()
        for child in children.get(branch_id, ()):
            child_id = int(child.get("id", -1))
            if child_id not in remove:
                remove.add(child_id)
                stack.append(child_id)
    return remove


def _upper_side_azimuth(parent, factor, rng):
    """Choose the side of a curved parent that points most upward in world space."""
    _point, _radius, tangent = generator._point_on_polyline(parent, factor)
    u, v = generator._basis(tangent)
    horizontal_energy = abs(float(u.z)) + abs(float(v.z))
    if horizontal_energy < 0.08:
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

    azimuth = _upper_side_azimuth(parent, factor, rng)
    return willow_architecture._make_lateral_branch(
        settings,
        parent,
        branch_id,
        rng,
        level=1,
        factor=factor,
        azimuth=azimuth,
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
    """Add obliquely upright structural laterals that later become weeping parents."""
    terminals = []
    if count <= 0:
        return next_id, terminals

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
            metadata={
                "willow_relay_scaffold": True,
                "willow_architecture_added": True,
            },
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
                metadata={
                    "willow_relay_scaffold": True,
                    "willow_architecture_added": True,
                },
            )
            next_id += 1
            branches.append(daughter)
            terminals.append(daughter)
        else:
            terminals.append(child)

    return next_id, terminals


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


def _prune_generic_upper_trunk(branches, trunk, cutoff_factor, protected_ids):
    """Remove generic subtrees whose top-level attachment would sit on the aborted trunk."""
    children = _children_map(branches)
    roots_to_remove = []
    trunk_id = int(trunk.get("id", 0))
    for branch in children.get(trunk_id, ()):
        branch_id = int(branch.get("id", -1))
        if branch_id in protected_ids or branch.get("willow_root_buttress", False):
            continue
        points = branch.get("points", ())
        if not points:
            continue
        factor = _closest_factor(trunk, points[0][0])
        if factor > cutoff_factor:
            roots_to_remove.append(branch_id)

    remove_ids = _descendant_ids(children, roots_to_remove)
    if not remove_ids:
        return branches, 0
    return [branch for branch in branches if int(branch.get("id", -1)) not in remove_ids], len(remove_ids)


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

    # A natural mature willow still has a basal trunk.  The first axis takeover
    # occurs well below mid-crown, then the parent axis ends soon after it.
    first_factor = rng.uniform(0.265, 0.325)
    first_relay = _make_relay(settings, trunk, next_id, rng, first_factor, second=False)
    next_id += 1
    branches.append(first_relay)

    next_id, _first_terminals = _add_relay_scaffolds(
        settings,
        branches,
        first_relay,
        next_id,
        rng,
        int(cfg["first_scaffolds"]),
        float(cfg["daughter_chance"]),
    )

    relay_axes = [first_relay]
    if relay_count >= 2:
        second_factor = rng.uniform(0.54, 0.66)
        second_relay = _make_relay(settings, first_relay, next_id, rng, second_factor, second=True)
        next_id += 1
        branches.append(second_relay)
        relay_axes.append(second_relay)
        next_id, _second_terminals = _add_relay_scaffolds(
            settings,
            branches,
            second_relay,
            next_id,
            rng,
            int(cfg["second_scaffolds"]),
            float(cfg["daughter_chance"]) * 0.86,
        )

    # Remove generic crown subtrees that were attached to the portion of trunk
    # which biologically no longer exists.  Keep the new relay and buttress roots.
    trunk_cutoff = min(0.42, first_factor + rng.uniform(0.050, 0.070))
    protected = {int(branch.get("id", -1)) for branch in relay_axes}
    branches, removed = _prune_generic_upper_trunk(branches, trunk, trunk_cutoff, protected)

    _truncate_branch(
        trunk,
        trunk_cutoff,
        minimum_tip_radius=max(float(settings.base_radius) * 0.020, 0.006),
    )

    terminals = _recompute_terminals(branches)
    trunk["willow_relay_architecture_version"] = 1
    trunk["willow_first_relay_fraction"] = float(first_factor)
    trunk["willow_trunk_cutoff_fraction"] = float(trunk_cutoff)
    trunk["willow_trunk_terminated"] = True
    trunk["willow_relay_count"] = len(relay_axes)
    trunk["willow_removed_upper_branch_records"] = int(removed)
    return branches, terminals


def prepare():
    """Disable the older forced co-dominant leaders before willow_architecture installs."""
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
