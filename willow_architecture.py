"""Mature weeping-willow structural architecture.

This module runs on WILLOW only.  It expands the generic botanical skeleton
with a small number of *real* medium/large branches before the hierarchy-aware
structural-motion stage runs:

* low co-dominant leaders break the single-pole silhouette,
* selected heavy scaffolds receive intermediate lateral forks,
* those forks receive a limited second generation of real woody descendants,
* low buttress roots make the base less cylindrical,
* non-terminal woody limbs can still act as cheap virtual foliage supports.

The added topology is deliberately sparse.  The generic generator already makes
hundreds of fine branches; what was missing visually was the medium-scale woody
hierarchy between the trunk and the drooping foliage curtains.
"""

import math
import random

from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False
_WORLD_UP = Vector((0.0, 0.0, 1.0))
_WORLD_DOWN = Vector((0.0, 0.0, -1.0))


_LOD_ARCHITECTURE = {
    "LOD0": dict(leaders=2, roots=5, scaffold_augments=8, leader_children=3, daughter_chance=0.72),
    "LOD1": dict(leaders=2, roots=4, scaffold_augments=6, leader_children=3, daughter_chance=0.60),
    "LOD2": dict(leaders=2, roots=3, scaffold_augments=4, leader_children=2, daughter_chance=0.42),
    "LOD3": dict(leaders=1, roots=0, scaffold_augments=2, leader_children=2, daughter_chance=0.25),
    "LOD4": dict(leaders=1, roots=0, scaffold_augments=0, leader_children=1, daughter_chance=0.0),
}


def _stable_unit(seed, value):
    x = (int(value) ^ int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def _safe_normalized(value, fallback):
    if value.length_squared <= 1.0e-12:
        return fallback.copy()
    return value.normalized()


def _new_id(branches):
    return max((int(branch.get("id", -1)) for branch in branches), default=-1) + 1


def _branch_record(branch_id, level, parent, points, rng, **metadata):
    branch = {
        "id": int(branch_id),
        "level": int(level),
        "parent_id": int(parent.get("id", -1)),
        "points": points,
        "dead": False,
        "phase": rng.random(),
        "length": 0.0,
    }
    branch.update(metadata)
    branch["length"] = generator._polyline_length(branch)
    return branch


def _make_lateral_branch(
    settings,
    parent,
    branch_id,
    rng,
    *,
    level,
    factor,
    azimuth,
    length_ratio,
    radius_ratio,
    forward,
    outward,
    upward,
    bend,
    droop,
    collar_scale=0.80,
    metadata=None,
):
    start, parent_radius, tangent = generator._point_on_polyline(parent, factor)
    u, v = generator._basis(tangent)
    radial = _safe_normalized(u * math.cos(azimuth) + v * math.sin(azimuth), u)
    direction = _safe_normalized(
        tangent * forward + radial * outward + _WORLD_UP * upward,
        radial,
    )

    parent_length = max(float(parent.get("length", generator._polyline_length(parent))), 0.05)
    length = parent_length * length_ratio
    minimum = float(settings.base_radius) * (0.012 if level <= 2 else 0.007)
    base_radius = max(parent_radius * radius_ratio, minimum)
    segment_factor = float(generator.LOD.get(str(settings.lod), generator.LOD["LOD0"])["segment_factor"])
    segments = max(4, round((10 - min(level, 4)) * segment_factor + length * 0.42))

    points = generator._branch_polyline(
        rng,
        start,
        direction,
        length,
        base_radius,
        segments,
        bend,
        droop,
        float(settings.phototropism) * 0.55,
        float(settings.branch_collar) * collar_scale,
    )
    return _branch_record(
        branch_id,
        level,
        parent,
        points,
        rng,
        **(metadata or {}),
    )


def _make_buttress_root(settings, trunk, branch_id, rng, azimuth, slot):
    # Attach just above the ground and explicitly solve the path toward z≈0 so
    # the result reads as a buttress/root rather than a low horizontal branch.
    factor = 0.010 + 0.006 * slot
    start, parent_radius, tangent = generator._point_on_polyline(trunk, factor)
    u, v = generator._basis(tangent)
    radial = _safe_normalized(u * math.cos(azimuth) + v * math.sin(azimuth), u)
    side = _safe_normalized(_WORLD_UP.cross(radial), v)

    length = float(settings.base_radius) * rng.uniform(2.0, 3.4)
    segments = 7 if str(settings.lod) == "LOD0" else 5
    base_radius = max(parent_radius * rng.uniform(0.28, 0.38), float(settings.base_radius) * 0.10)
    points = []
    phase = rng.uniform(0.0, math.tau)
    for index in range(segments + 1):
        t = index / max(segments, 1)
        lateral = side * math.sin(phase + t * math.pi * 1.35) * length * 0.08 * t
        forward = radial * length * (t ** 0.92)
        # Strong raised shoulder near the trunk, then settle into the terrain.
        z = max(0.018, float(start.z) * ((1.0 - t) ** 1.55) + 0.018 * t)
        point = Vector((start.x, start.y, z)) + forward + lateral
        radius = max(base_radius * ((1.0 - t) ** 1.28), float(settings.base_radius) * 0.012)
        points.append((point, radius))

    return _branch_record(
        branch_id,
        1,
        trunk,
        points,
        rng,
        willow_root_buttress=True,
        willow_no_foliage=True,
        willow_architecture_added=True,
    )


def _add_codominant_leaders(settings, branches, terminals, next_id, cfg):
    trunk = branches[0]
    rng = random.Random(int(settings.seed) ^ 0xC0D011A)
    leader_count = int(cfg["leaders"])
    new_terminals = []
    leaders = []

    # Sector placement prevents another evenly spaced spoke crown.  The sectors
    # are broad, deterministic and deliberately asymmetric.
    sector_phase = rng.uniform(0.0, math.tau)
    for leader_index in range(leader_count):
        factor = rng.uniform(0.27, 0.43) + leader_index * rng.uniform(0.035, 0.070)
        factor = min(0.56, factor)
        sector = sector_phase + leader_index * (math.tau / max(leader_count + 1, 3))
        azimuth = sector + rng.uniform(-0.38, 0.38)
        leader = _make_lateral_branch(
            settings,
            trunk,
            next_id,
            rng,
            level=1,
            factor=factor,
            azimuth=azimuth,
            length_ratio=rng.uniform(0.47, 0.61),
            radius_ratio=rng.uniform(0.50, 0.59),
            forward=rng.uniform(0.52, 0.66),
            outward=rng.uniform(0.70, 0.88),
            upward=rng.uniform(0.10, 0.23),
            bend=float(settings.branch_bend) * 0.65,
            droop=float(settings.branch_droop) * 0.35,
            collar_scale=1.15,
            metadata={
                "willow_codominant": True,
                "willow_architecture_added": True,
            },
        )
        next_id += 1
        branches.append(leader)
        leaders.append(leader)

        child_count = int(cfg["leader_children"])
        child_terminals = []
        for child_index in range(child_count):
            child_factor = 0.34 + 0.54 * ((child_index + rng.uniform(0.20, 0.78)) / max(child_count, 1))
            child_factor = min(0.90, child_factor)
            child_azimuth = azimuth + rng.choice((-1.0, 1.0)) * rng.uniform(0.75, 1.55)
            child = _make_lateral_branch(
                settings,
                leader,
                next_id,
                rng,
                level=2,
                factor=child_factor,
                azimuth=child_azimuth,
                length_ratio=rng.uniform(0.40, 0.56),
                radius_ratio=rng.uniform(0.34, 0.43),
                forward=rng.uniform(0.34, 0.52),
                outward=rng.uniform(0.76, 0.96),
                upward=rng.uniform(-0.03, 0.09),
                bend=float(settings.branch_bend) * 0.82,
                droop=float(settings.branch_droop) * 0.78,
                metadata={
                    "willow_structural_fork": True,
                    "willow_architecture_added": True,
                },
            )
            next_id += 1
            branches.append(child)

            if rng.random() < float(cfg["daughter_chance"]):
                daughter = _make_lateral_branch(
                    settings,
                    child,
                    next_id,
                    rng,
                    level=3,
                    factor=rng.uniform(0.48, 0.78),
                    azimuth=child_azimuth + rng.choice((-1.0, 1.0)) * rng.uniform(0.70, 1.35),
                    length_ratio=rng.uniform(0.40, 0.52),
                    radius_ratio=rng.uniform(0.32, 0.40),
                    forward=rng.uniform(0.28, 0.46),
                    outward=rng.uniform(0.78, 0.98),
                    upward=rng.uniform(-0.08, 0.04),
                    bend=float(settings.branch_bend) * 0.95,
                    droop=float(settings.branch_droop) * 1.10,
                    collar_scale=0.72,
                    metadata={
                        "willow_structural_fork": True,
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
    return next_id, leaders


def _augment_existing_scaffolds(settings, branches, terminals, next_id, cfg):
    rng = random.Random(int(settings.seed) ^ 0x51CAFF01)
    candidates = [
        branch for branch in branches
        if int(branch.get("level", 0)) == 1
        and not branch.get("dead", False)
        and not branch.get("willow_root_buttress", False)
        and not branch.get("willow_codominant", False)
        and len(branch.get("points", ())) >= 3
    ]
    # Long/thick existing primaries are exactly the exposed beams visible in the
    # comparison screenshot, so target those rather than adding branches everywhere.
    candidates.sort(
        key=lambda branch: float(branch.get("length", 0.0)) * float(branch["points"][0][1]),
        reverse=True,
    )
    candidates = candidates[: int(cfg["scaffold_augments"])]
    new_terminals = []

    for rank, parent in enumerate(candidates):
        branch_seed = int(settings.seed) ^ (int(parent.get("id", 0)) * 0x45D9F3B)
        local = random.Random(branch_seed ^ 0xA09F0A)
        additions = 2 if rank < max(2, len(candidates) // 3) and str(settings.lod) in {"LOD0", "LOD1"} else 1
        for addition in range(additions):
            factor = local.uniform(0.38, 0.80)
            azimuth = local.uniform(0.0, math.tau)
            child = _make_lateral_branch(
                settings,
                parent,
                next_id,
                local,
                level=2,
                factor=factor,
                azimuth=azimuth,
                length_ratio=local.uniform(0.36, 0.52),
                radius_ratio=local.uniform(0.32, 0.40),
                forward=local.uniform(0.32, 0.52),
                outward=local.uniform(0.76, 0.98),
                upward=local.uniform(-0.05, 0.08),
                bend=float(settings.branch_bend) * 0.82,
                droop=float(settings.branch_droop) * 0.82,
                metadata={
                    "willow_scaffold_fill": True,
                    "willow_architecture_added": True,
                },
            )
            next_id += 1
            branches.append(child)

            if local.random() < float(cfg["daughter_chance"]) * 0.82:
                daughter = _make_lateral_branch(
                    settings,
                    child,
                    next_id,
                    local,
                    level=3,
                    factor=local.uniform(0.48, 0.80),
                    azimuth=azimuth + local.choice((-1.0, 1.0)) * local.uniform(0.65, 1.45),
                    length_ratio=local.uniform(0.38, 0.52),
                    radius_ratio=local.uniform(0.31, 0.39),
                    forward=local.uniform(0.25, 0.44),
                    outward=local.uniform(0.78, 1.00),
                    upward=local.uniform(-0.09, 0.03),
                    bend=float(settings.branch_bend),
                    droop=float(settings.branch_droop) * 1.18,
                    collar_scale=0.70,
                    metadata={
                        "willow_scaffold_fill": True,
                        "willow_architecture_added": True,
                    },
                )
                next_id += 1
                branches.append(daughter)
                new_terminals.append(daughter)
            else:
                new_terminals.append(child)

    terminals.extend(new_terminals)
    return next_id


def _add_buttress_roots(settings, branches, next_id, cfg):
    count = int(cfg["roots"])
    if count <= 0:
        return next_id
    trunk = branches[0]
    rng = random.Random(int(settings.seed) ^ 0xB077AE55)
    phase = rng.uniform(0.0, math.tau)
    for index in range(count):
        azimuth = phase + index * math.tau / count + rng.uniform(-0.22, 0.22)
        root = _make_buttress_root(settings, trunk, next_id, rng, azimuth, index)
        next_id += 1
        branches.append(root)
    return next_id


def _anchor_metadata(branch):
    level = int(branch.get("level", 0))
    if branch.get("willow_architecture_added", False):
        if level <= 1:
            return 0.44, 0.50, 2
        if level == 2:
            return 0.72, 0.68, 3
        return 0.58, 0.78, 2
    if level <= 1:
        return 0.30, 0.50, 2
    if level == 2:
        return 0.54, 0.66, 3
    return 0.45, 0.76, 2


def _add_virtual_foliage_anchors(settings, branches, terminals):
    existing_ids = {int(branch.get("id", -1)) for branch in terminals}
    extras = []
    height = max(float(settings.height), 1.0e-5)
    radial_reference = max(float(settings.branch_length), float(settings.base_radius) * 4.0, 1.0e-4)

    for branch in branches:
        branch_id = int(branch.get("id", -1))
        level = int(branch.get("level", 0))
        if (
            branch_id in existing_ids
            or level < 1
            or level > 3
            or branch.get("dead", False)
            or branch.get("willow_no_foliage", False)
        ):
            continue
        if len(branch.get("points", ())) < 2:
            continue

        p_mid, _r, _t = generator._point_on_polyline(branch, 0.62)
        p_end = branch["points"][-1][0]
        h = max(float(p_mid.z), float(p_end.z)) / height
        radial = max(
            math.hypot(float(p_mid.x), float(p_mid.y)),
            math.hypot(float(p_end.x), float(p_end.y)),
        ) / radial_reference
        if h < 0.26:
            continue

        base_probability = {1: 0.82, 2: 0.72, 3: 0.46}[level]
        if branch.get("willow_architecture_added", False):
            base_probability += 0.10
        probability = base_probability * (0.78 + 0.30 * min(1.0, radial))
        probability *= 0.76 + 0.30 * min(1.0, max(0.0, (h - 0.26) / 0.50))
        if _stable_unit(int(settings.seed) ^ 0x51A10A, branch_id * 53 + level * 17) > min(0.98, probability):
            continue

        weight, length_scale, max_bundles = _anchor_metadata(branch)
        branch["willow_aux_anchor"] = True
        branch["willow_anchor_weight"] = float(weight)
        branch["willow_length_scale"] = float(length_scale)
        branch["willow_fill_only"] = True
        branch["willow_max_bundles"] = int(max_bundles)
        branch["willow_anchor_level"] = int(level)
        extras.append(branch)
        existing_ids.add(branch_id)

    terminals.extend(extras)
    return extras


def _generate_with_willow_architecture(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    terminals = list(terminals)
    cfg = _LOD_ARCHITECTURE.get(str(settings.lod), _LOD_ARCHITECTURE["LOD0"])
    next_id = _new_id(branches)
    original_branch_count = len(branches)

    next_id = _add_buttress_roots(settings, branches, next_id, cfg)
    next_id, leaders = _add_codominant_leaders(settings, branches, terminals, next_id, cfg)
    next_id = _augment_existing_scaffolds(settings, branches, terminals, next_id, cfg)
    extras = _add_virtual_foliage_anchors(settings, branches, terminals)

    try:
        trunk = branches[0]
        trunk["willow_architecture_version"] = 2
        trunk["willow_added_real_branch_count"] = len(branches) - original_branch_count
        trunk["willow_codominant_count"] = len(leaders)
        trunk["willow_virtual_anchor_count"] = len(extras)
        trunk["willow_real_terminal_count"] = len(terminals) - len(extras)
    except Exception:
        pass

    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_willow_architecture
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
