"""Hierarchy-aware structural motion for mature weeping willows.

The generic growth system provides topology, radii and botanical hierarchy.  This
module changes only WILLOW branch trajectories after the normal skeleton has
been generated.  It deliberately uses smooth correlated motion rather than
per-segment random jitter:

* the trunk gets a slow serpentine lean and lower-trunk wander,
* primary scaffolds get broad sweeping arcs and asymmetric wandering,
* secondary branches inherit the deformed parent frame and become more chaotic,
* tertiary/fine branches receive stronger multi-scale wandering and distal droop,
* child attachment points are remapped onto the already-deformed parent so
  junctions remain connected,
* branch radii are preserved and branch lengths are recomputed.

The wrapper is installed before willow_architecture.  Therefore the virtual
foliage-anchor selection sees the final curved skeleton rather than the old
straight one.
"""

import math

from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False

_WORLD_UP = Vector((0.0, 0.0, 1.0))
_WORLD_DOWN = Vector((0.0, 0.0, -1.0))


# Direction-field amplitudes.  They are intentionally dimensionless: branch
# segment lengths still come from the botanical generator, so the same values
# scale naturally with differently sized trees.
_LEVEL_PARAMS = {
    0: dict(arc=0.145, wander=0.090, micro=0.032, droop=0.000, response=0.32, droop_start=1.00),
    1: dict(arc=0.315, wander=0.205, micro=0.060, droop=0.255, response=0.38, droop_start=0.48),
    2: dict(arc=0.285, wander=0.305, micro=0.095, droop=0.455, response=0.43, droop_start=0.40),
    3: dict(arc=0.235, wander=0.405, micro=0.135, droop=0.670, response=0.49, droop_start=0.32),
    4: dict(arc=0.195, wander=0.455, micro=0.155, droop=0.790, response=0.53, droop_start=0.28),
}


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _smoothstep(lo, hi, value):
    if hi <= lo:
        return 1.0 if value >= hi else 0.0
    t = _clamp((value - lo) / (hi - lo))
    return t * t * (3.0 - 2.0 * t)


def _safe_normalized(value, fallback):
    if value.length_squared <= 1.0e-12:
        return fallback.copy()
    return value.normalized()


def _hash_unit(seed, value):
    x = (int(value) ^ int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def _value_noise(x, seed):
    i0 = math.floor(x)
    f = x - i0
    # Quintic interpolation avoids visible changes of curvature at lattice cells.
    u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)
    a = _hash_unit(seed, i0 * 92821 + 17) * 2.0 - 1.0
    b = _hash_unit(seed, (i0 + 1) * 92821 + 17) * 2.0 - 1.0
    return a + (b - a) * u


def _fbm(x, seed, octaves=4):
    total = 0.0
    norm = 0.0
    amplitude = 1.0
    frequency = 1.0
    for octave in range(octaves):
        total += _value_noise(x * frequency + octave * 11.731, seed + octave * 1009) * amplitude
        norm += amplitude
        amplitude *= 0.50
        frequency *= 2.03
    return total / max(norm, 1.0e-8)


def _points(branch):
    return [point.copy() for point, _radius in branch.get("points", ())]


def _radii(branch):
    return [float(radius) for _point, radius in branch.get("points", ())]


def _polyline_lengths(points):
    cumulative = [0.0]
    total = 0.0
    for index in range(len(points) - 1):
        total += (points[index + 1] - points[index]).length
        cumulative.append(total)
    return cumulative, total


def _sample_polyline(points, factor):
    if not points:
        return Vector((0.0, 0.0, 0.0)), _WORLD_UP.copy()
    if len(points) == 1:
        return points[0].copy(), _WORLD_UP.copy()

    cumulative, total = _polyline_lengths(points)
    if total <= 1.0e-8:
        tangent = _safe_normalized(points[-1] - points[0], _WORLD_UP)
        return points[0].copy(), tangent

    target = _clamp(factor) * total
    segment = 0
    while segment + 1 < len(cumulative) and cumulative[segment + 1] < target:
        segment += 1
    segment = min(segment, len(points) - 2)
    seg_start = cumulative[segment]
    seg_length = max(cumulative[segment + 1] - seg_start, 1.0e-8)
    local = _clamp((target - seg_start) / seg_length)
    tangent = _safe_normalized(points[segment + 1] - points[segment], _WORLD_UP)
    return points[segment].lerp(points[segment + 1], local), tangent


def _closest_factor(points, target):
    """Arc-length factor of the closest projection of target onto a polyline."""
    if len(points) < 2:
        return 0.0
    cumulative, total = _polyline_lengths(points)
    if total <= 1.0e-8:
        return 0.0

    best_distance = float("inf")
    best_length = 0.0
    for index in range(len(points) - 1):
        a = points[index]
        delta = points[index + 1] - a
        length_sq = delta.length_squared
        if length_sq <= 1.0e-12:
            local = 0.0
            projected = a
        else:
            local = _clamp((target - a).dot(delta) / length_sq)
            projected = a + delta * local
        distance = (target - projected).length_squared
        if distance < best_distance:
            best_distance = distance
            segment_length = math.sqrt(max(length_sq, 0.0))
            best_length = cumulative[index] + segment_length * local
    return _clamp(best_length / total)


def _basis(direction, seed):
    tangent = _safe_normalized(direction, _WORLD_UP)
    side, up = generator._basis(tangent)
    # Rotate the bend basis deterministically around the branch axis.  This
    # prevents every scaffold from bowing in the same local direction.
    phase = _hash_unit(seed, 31337) * math.tau
    first = side * math.cos(phase) + up * math.sin(phase)
    second = -side * math.sin(phase) + up * math.cos(phase)
    return _safe_normalized(first, side), _safe_normalized(second, up)


def _level_params(level):
    return _LEVEL_PARAMS.get(min(max(int(level), 0), 4), _LEVEL_PARAMS[4])


def _deform_path(source_points, level, branch_id, tree_seed, tree_height):
    """Integrate a smooth, correlated direction field while preserving segment lengths."""
    if len(source_points) < 3:
        return [point.copy() for point in source_points]

    cumulative, total_length = _polyline_lengths(source_points)
    if total_length <= 1.0e-8:
        return [point.copy() for point in source_points]

    params = _level_params(level)
    seed = int(tree_seed) ^ (int(branch_id) * 0x45D9F3B) ^ (int(level) * 7919)

    base_direction = _safe_normalized(source_points[1] - source_points[0], _WORLD_UP)
    bend_a, bend_b = _basis(base_direction, seed)
    sweep_phase = (_hash_unit(seed, 8191) * 2.0 - 1.0) * 0.70
    asymmetry = 0.80 + 0.40 * _hash_unit(seed, 23743)

    # Short fine branches can tolerate proportionally more angular motion.  On
    # large primary limbs we temper the high-frequency component so the result
    # remains a graceful willow scaffold rather than a crumpled wire.
    relative_length = total_length / max(float(tree_height), 1.0e-5)
    short_boost = 1.0 + 0.22 * (1.0 - _smoothstep(0.08, 0.34, relative_length))

    result = [source_points[0].copy()]
    current_direction = base_direction.copy()

    for index in range(len(source_points) - 1):
        original_delta = source_points[index + 1] - source_points[index]
        segment_length = original_delta.length
        if segment_length <= 1.0e-9:
            result.append(result[-1].copy())
            continue

        t0 = cumulative[index] / total_length
        t1 = cumulative[index + 1] / total_length
        t = (t0 + t1) * 0.5
        original_tangent = original_delta / segment_length

        # A broad, one-sided sweep gives the heavy limbs their characteristic
        # arch.  FBM then adds correlated multi-scale wandering without sharp
        # random kinks.
        broad = math.sin(math.pi * _clamp(t + sweep_phase * 0.08))
        broad *= 0.58 + 0.42 * math.sin(math.pi * t)
        n1 = _fbm(t * 2.25 + 0.17, seed + 101, 4)
        n2 = _fbm(t * 2.70 + 3.31, seed + 307, 4)
        m1 = _fbm(t * 6.80 + 1.73, seed + 601, 3)
        m2 = _fbm(t * 7.90 + 5.47, seed + 907, 3)

        root_gate = _smoothstep(0.015, 0.18, t)
        outer_gate = _smoothstep(0.10, 0.92, t)
        tip_gate = _smoothstep(float(params["droop_start"]), 1.0, t)

        target = original_tangent.copy()
        target += bend_a * (broad * float(params["arc"]) * asymmetry * root_gate)
        target += bend_a * (n1 * float(params["wander"]) * outer_gate * short_boost)
        target += bend_b * (n2 * float(params["wander"]) * 0.72 * outer_gate * short_boost)
        target += bend_a * (m1 * float(params["micro"]) * outer_gate)
        target += bend_b * (m2 * float(params["micro"]) * 0.82 * outer_gate)

        if level == 0:
            # The lower trunk should already be visibly organic before the crown
            # begins.  A second ultra-low-frequency component produces a slow
            # serpentine lean while leaving the root origin fixed.
            lower_motion = _smoothstep(0.025, 0.33, t) * (1.0 - 0.22 * _smoothstep(0.72, 1.0, t))
            target += bend_a * (_fbm(t * 1.12 + 2.0, seed + 1301, 3) * 0.13 * lower_motion)
            target += bend_b * (_fbm(t * 1.37 + 6.0, seed + 1601, 3) * 0.10 * lower_motion)
        else:
            # Distal gravity is intentionally progressive: heavy scaffolds stay
            # arched, while finer descendants become strongly pendulous.
            target += _WORLD_DOWN * (float(params["droop"]) * tip_gate * tip_gate)

        target = _safe_normalized(target, original_tangent)

        # Direction inertia is the key to smooth botanical curvature.  It keeps
        # adjacent segments correlated even when the higher-frequency field
        # changes sign.
        response = float(params["response"])
        if index == 0:
            response *= 0.58
        current_direction = _safe_normalized(
            current_direction.lerp(target, _clamp(response, 0.05, 0.85)),
            target,
        )
        result.append(result[-1] + current_direction * segment_length)

    # One conservative positional fairing pass removes any residual polygonal
    # feel while keeping the branch origin exact.  The tip stays free so its
    # gravity-induced droop is not pulled back toward the previous segment.
    if len(result) >= 4:
        smoothed = [point.copy() for point in result]
        for index in range(1, len(result) - 1):
            weight = 0.16 if level <= 1 else 0.11
            neighborhood = (result[index - 1] + result[index + 1]) * 0.5
            smoothed[index] = result[index].lerp(neighborhood, weight)
        smoothed[0] = result[0].copy()
        result = smoothed

    return result


def _transform_child_to_parent(original_points, old_parent, new_parent):
    """Move/rotate a child into the deformed parent's attachment frame."""
    if not original_points or len(old_parent) < 2 or len(new_parent) < 2:
        return [point.copy() for point in original_points]

    old_start = original_points[0]
    factor = _closest_factor(old_parent, old_start)
    old_attach, old_tangent = _sample_polyline(old_parent, factor)
    new_attach, new_tangent = _sample_polyline(new_parent, factor)

    try:
        rotation = old_tangent.rotation_difference(new_tangent)
    except Exception:
        rotation = None

    transformed = []
    for point in original_points:
        offset = point - old_start
        if rotation is not None:
            offset = rotation @ offset
        transformed.append(new_attach + offset)
    transformed[0] = new_attach.copy()
    return transformed


def _deform_willow_hierarchy(branches, settings):
    if not branches:
        return branches

    original = {
        int(branch.get("id", index)): _points(branch)
        for index, branch in enumerate(branches)
    }
    by_id = {
        int(branch.get("id", index)): branch
        for index, branch in enumerate(branches)
    }
    deformed = {}

    ordered = sorted(
        branches,
        key=lambda branch: (int(branch.get("level", 0)), int(branch.get("id", 0))),
    )

    for branch in ordered:
        branch_id = int(branch.get("id", 0))
        level = int(branch.get("level", 0))
        parent_id = int(branch.get("parent_id", -1))
        source = [point.copy() for point in original.get(branch_id, ())]
        if len(source) < 2:
            continue

        if level > 0 and parent_id in original and parent_id in deformed:
            source = _transform_child_to_parent(source, original[parent_id], deformed[parent_id])

        warped = _deform_path(
            source,
            level,
            branch_id,
            int(settings.seed),
            float(settings.height),
        )
        deformed[branch_id] = warped

        radii = _radii(branch)
        # Preserve the source radial profile exactly.  Position-only deformation
        # means branch-profile, exact-junction and wind metadata remain valid.
        if len(radii) != len(warped):
            radii = [float(branch["points"][min(i, len(branch["points"]) - 1)][1]) for i in range(len(warped))]
        branch["points"] = [(point.copy(), radii[index]) for index, point in enumerate(warped)]
        branch["length"] = generator._polyline_length(branch)
        branch["willow_structure_motion"] = True
        branch["willow_motion_version"] = 1

    try:
        trunk = by_id.get(0, ordered[0])
        trunk["willow_motion_branch_count"] = sum(
            1 for branch in branches if branch.get("willow_structure_motion", False)
        )
    except Exception:
        pass
    return branches


def _generate_with_motion(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW":
        return branches, terminals

    _deform_willow_hierarchy(branches, settings)
    # terminals contains references to the same branch dictionaries, therefore
    # it automatically observes the updated point paths.
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_motion
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
