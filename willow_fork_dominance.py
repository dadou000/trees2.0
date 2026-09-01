"""Low multi-leader fork architecture for mature weeping willow.

The generic generator always contains a trunk branch from ground to crown.  Even
with extra lateral branches, that continuous thick spine made the willow read as
"one trunk with branches" instead of an old tree that divides into several
co-dominant leaders.

This stage runs after willow_architecture and before hierarchy-aware structural
motion.  It does two things:

1. adds a small number of additional heavy leaders in the largest empty angular
   sectors around the low/middle trunk, with real secondary/daughter forks;
2. strongly subordinates the radius of the original trunk above the fork zone,
   leaving it as just one slender crown leader rather than the dominant spine.

All added branches are real branch records and are subsequently processed by
willow_structure_motion, crown spreading, junction generation and foliage.
"""

import math
import random

from . import generator, willow_architecture


_PREVIOUS_GENERATE = None
_INSTALLED = False


_LOD_FORKS = {
    "LOD0": dict(extra_leaders=2, children=3, daughter_chance=0.72),
    "LOD1": dict(extra_leaders=2, children=3, daughter_chance=0.58),
    "LOD2": dict(extra_leaders=1, children=2, daughter_chance=0.38),
    "LOD3": dict(extra_leaders=0, children=0, daughter_chance=0.0),
    "LOD4": dict(extra_leaders=0, children=0, daughter_chance=0.0),
}


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _smoothstep(lo, hi, value):
    if hi <= lo:
        return 1.0 if value >= hi else 0.0
    t = _clamp((value - lo) / (hi - lo))
    return t * t * (3.0 - 2.0 * t)


def _new_id(branches):
    return max((int(branch.get("id", -1)) for branch in branches), default=-1) + 1


def _branch_azimuth(branch):
    points = branch.get("points", ())
    if len(points) < 2:
        return None
    start = points[0][0]
    # Sample far enough from the collar that local parent alignment does not
    # dominate the sector estimate.
    try:
        sample, _radius, _tangent = generator._point_on_polyline(branch, 0.28)
    except Exception:
        sample = points[min(len(points) - 1, 2)][0]
    dx = float(sample.x - start.x)
    dy = float(sample.y - start.y)
    if dx * dx + dy * dy < 1.0e-8:
        return None
    return math.atan2(dy, dx) % math.tau


def _largest_gap_midpoints(angles, count, phase):
    """Choose new leader sectors from the largest gaps in existing scaffolds."""
    if count <= 0:
        return []
    values = sorted(angle % math.tau for angle in angles if angle is not None)
    if not values:
        return [(phase + math.tau * i / count) % math.tau for i in range(count)]

    chosen = []
    working = list(values)
    for _ in range(count):
        working.sort()
        gaps = []
        for index, angle in enumerate(working):
            nxt = working[(index + 1) % len(working)]
            if index == len(working) - 1:
                nxt += math.tau
            gaps.append((nxt - angle, angle, nxt))
        _gap, start, end = max(gaps, key=lambda item: item[0])
        midpoint = ((start + end) * 0.5) % math.tau
        chosen.append(midpoint)
        working.append(midpoint)
    return chosen


def _add_fork_leaders(settings, branches, terminals, cfg):
    count = int(cfg["extra_leaders"])
    if count <= 0 or not branches:
        return []

    trunk = branches[0]
    rng = random.Random(int(settings.seed) ^ 0xF04D0A11)
    existing = [
        branch for branch in branches
        if int(branch.get("level", 0)) == 1
        and int(branch.get("parent_id", -1)) == int(trunk.get("id", 0))
        and not branch.get("willow_root_buttress", False)
        and len(branch.get("points", ())) >= 2
    ]
    angles = [_branch_azimuth(branch) for branch in existing]
    sectors = _largest_gap_midpoints(angles, count, rng.uniform(0.0, math.tau))

    next_id = _new_id(branches)
    leaders = []
    new_terminals = []

    for leader_index, sector in enumerate(sectors):
        # Stagger the fork heights so the base reads as an irregular multi-stem
        # split rather than several branches emitted from one perfect node.
        factor = rng.uniform(0.29, 0.40) + leader_index * rng.uniform(0.025, 0.050)
        factor = min(0.48, factor)
        azimuth = sector + rng.uniform(-0.22, 0.22)

        leader = willow_architecture._make_lateral_branch(
            settings,
            trunk,
            next_id,
            rng,
            level=1,
            factor=factor,
            azimuth=azimuth,
            length_ratio=rng.uniform(0.50, 0.64),
            radius_ratio=rng.uniform(0.56, 0.67),
            forward=rng.uniform(0.44, 0.58),
            outward=rng.uniform(0.82, 0.98),
            upward=rng.uniform(0.12, 0.27),
            bend=float(settings.branch_bend) * rng.uniform(0.68, 0.88),
            droop=float(settings.branch_droop) * rng.uniform(0.22, 0.38),
            collar_scale=1.20,
            metadata={
                "willow_codominant": True,
                "willow_low_fork_leader": True,
                "willow_architecture_added": True,
            },
        )
        next_id += 1
        branches.append(leader)
        leaders.append(leader)

        child_count = int(cfg["children"])
        child_terminals = []
        for child_index in range(child_count):
            u = (child_index + rng.uniform(0.25, 0.82)) / max(child_count, 1)
            child_factor = _clamp(0.30 + 0.58 * u, 0.30, 0.90)
            child_azimuth = azimuth + rng.choice((-1.0, 1.0)) * rng.uniform(0.72, 1.50)
            child = willow_architecture._make_lateral_branch(
                settings,
                leader,
                next_id,
                rng,
                level=2,
                factor=child_factor,
                azimuth=child_azimuth,
                length_ratio=rng.uniform(0.42, 0.58),
                radius_ratio=rng.uniform(0.35, 0.45),
                forward=rng.uniform(0.30, 0.48),
                outward=rng.uniform(0.80, 1.00),
                upward=rng.uniform(-0.04, 0.08),
                bend=float(settings.branch_bend) * rng.uniform(0.84, 1.08),
                droop=float(settings.branch_droop) * rng.uniform(0.72, 0.98),
                collar_scale=0.84,
                metadata={
                    "willow_structural_fork": True,
                    "willow_low_fork_descendant": True,
                    "willow_architecture_added": True,
                },
            )
            next_id += 1
            branches.append(child)

            if rng.random() < float(cfg["daughter_chance"]):
                daughter = willow_architecture._make_lateral_branch(
                    settings,
                    child,
                    next_id,
                    rng,
                    level=3,
                    factor=rng.uniform(0.46, 0.78),
                    azimuth=child_azimuth + rng.choice((-1.0, 1.0)) * rng.uniform(0.65, 1.35),
                    length_ratio=rng.uniform(0.40, 0.54),
                    radius_ratio=rng.uniform(0.31, 0.40),
                    forward=rng.uniform(0.24, 0.42),
                    outward=rng.uniform(0.82, 1.00),
                    upward=rng.uniform(-0.10, 0.03),
                    bend=float(settings.branch_bend) * rng.uniform(0.95, 1.20),
                    droop=float(settings.branch_droop) * rng.uniform(1.05, 1.30),
                    collar_scale=0.72,
                    metadata={
                        "willow_structural_fork": True,
                        "willow_low_fork_descendant": True,
                        "willow_architecture_added": True,
                    },
                )
                next_id += 1
                branches.append(daughter)
                child_terminals.append(daughter)
            else:
                child_terminals.append(child)

        new_terminals.extend(child_terminals)

    terminals.extend(new_terminals)
    return leaders


def _subordinate_main_trunk(trunk):
    """Turn the upper original trunk into one minor leader after the fork zone."""
    points = trunk.get("points", ())
    if len(points) < 3:
        return

    cumulative = [0.0]
    total = 0.0
    for index in range(1, len(points)):
        total += (points[index][0] - points[index - 1][0]).length
        cumulative.append(total)
    if total <= 1.0e-6:
        return

    new_points = []
    for index, (point, radius) in enumerate(points):
        t = cumulative[index] / total
        # Full trunk below the fork.  Between 34% and 72% height it rapidly
        # yields diameter to the co-dominant leaders; above that it is only a
        # slender continuation instead of the main visual spine.
        dominance = 1.0 - 0.84 * _smoothstep(0.34, 0.74, t)
        # Avoid a numerical needle while still making the visual hierarchy clear.
        dominance = max(0.14, dominance)
        new_points.append((point.copy(), float(radius) * dominance))

    trunk["points"] = new_points
    trunk["length"] = generator._polyline_length(trunk)
    trunk["willow_upper_trunk_subordinated"] = True
    trunk["willow_main_fork_fraction"] = 0.34
    trunk["willow_upper_trunk_dominance"] = 0.16


def _generate_with_fork_dominance(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    terminals = list(terminals)
    cfg = _LOD_FORKS.get(str(settings.lod), _LOD_FORKS["LOD0"])

    # Leaders need the original trunk radius at their attachment points, so add
    # them first and subordinate the central trunk only afterward.
    leaders = _add_fork_leaders(settings, branches, terminals, cfg)
    _subordinate_main_trunk(branches[0])

    try:
        trunk = branches[0]
        trunk["willow_fork_dominance_version"] = 1
        trunk["willow_extra_low_fork_leaders"] = len(leaders)
    except Exception:
        pass
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_fork_dominance
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
