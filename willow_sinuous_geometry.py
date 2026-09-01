"""Adaptive smooth/sinuous centerlines for mature weeping willow.

The botanical willow stages already create the correct hierarchy, but their
branch records are still polylines with relatively few axial samples.  Moving
those sparse samples can make a branch bend, yet the bark mesh still bridges
long straight spans between rings.

This stage runs after hierarchy-aware willow structural motion and before crown
spreading.  It concentrates extra samples only in the woody axes that need them:
trunk/relay axes, primary scaffolds and selected structural secondaries.

Two operations are combined:
* endpoint-preserving Chaikin fairing + uniform arc-length resampling removes
  polygonal elbows while keeping the branch origin exact;
* a deterministic low-frequency 3D meander adds alternating curvature (broad
  S-curves) rather than high-frequency random jitter.

Children are remapped to the processed parent attachment frame before their own
curve is generated, so junctions remain coincident.
"""

import math

from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False
_WORLD_UP = Vector((0.0, 0.0, 1.0))


_LOD_SPACING = {
    "LOD0": {0: 0.018, 1: 0.024, 2: 0.034},
    "LOD1": {0: 0.026, 1: 0.034, 2: 0.046},
    "LOD2": {0: 0.038, 1: 0.050, 2: 0.065},
    "LOD3": {0: 0.060, 1: 0.078, 2: 0.095},
    "LOD4": {0: 0.095, 1: 0.120, 2: 0.150},
}

_MAX_POINTS = {
    "LOD0": {0: 48, 1: 34, 2: 20},
    "LOD1": {0: 38, 1: 27, 2: 16},
    "LOD2": {0: 28, 1: 21, 2: 13},
    "LOD3": {0: 20, 1: 15, 2: 10},
    "LOD4": {0: 14, 1: 11, 2: 8},
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
    x = (int(seed) ^ int(value) ^ 0x9E3779B9) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def _pairs(branch):
    return [(point.copy(), float(radius)) for point, radius in branch.get("points", ())]


def _polyline_lengths(pairs):
    cumulative = [0.0]
    total = 0.0
    for index in range(len(pairs) - 1):
        total += (pairs[index + 1][0] - pairs[index][0]).length
        cumulative.append(total)
    return cumulative, total


def _sample_pair(pairs, factor):
    if not pairs:
        return Vector((0.0, 0.0, 0.0)), 0.0, _WORLD_UP.copy()
    if len(pairs) == 1:
        return pairs[0][0].copy(), float(pairs[0][1]), _WORLD_UP.copy()

    cumulative, total = _polyline_lengths(pairs)
    if total <= 1.0e-8:
        tangent = _safe_normalized(pairs[-1][0] - pairs[0][0], _WORLD_UP)
        return pairs[0][0].copy(), float(pairs[0][1]), tangent

    target = _clamp(factor) * total
    segment = 0
    while segment + 1 < len(cumulative) and cumulative[segment + 1] < target:
        segment += 1
    segment = min(segment, len(pairs) - 2)
    start_distance = cumulative[segment]
    span = max(cumulative[segment + 1] - start_distance, 1.0e-8)
    local = _clamp((target - start_distance) / span)
    p0, r0 = pairs[segment]
    p1, r1 = pairs[segment + 1]
    tangent = _safe_normalized(p1 - p0, _WORLD_UP)
    return p0.lerp(p1, local), r0 + (r1 - r0) * local, tangent


def _closest_factor(pairs, target):
    if len(pairs) < 2:
        return 0.0
    cumulative, total = _polyline_lengths(pairs)
    if total <= 1.0e-8:
        return 0.0

    best_distance = float("inf")
    best_length = 0.0
    for index in range(len(pairs) - 1):
        a = pairs[index][0]
        delta = pairs[index + 1][0] - a
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


def _chaikin_once(pairs):
    if len(pairs) < 3:
        return [(point.copy(), float(radius)) for point, radius in pairs]

    output = [(pairs[0][0].copy(), float(pairs[0][1]))]
    for index in range(len(pairs) - 1):
        p0, r0 = pairs[index]
        p1, r1 = pairs[index + 1]
        q = p0.lerp(p1, 0.25)
        rq = r0 + (r1 - r0) * 0.25
        r = p0.lerp(p1, 0.75)
        rr = r0 + (r1 - r0) * 0.75
        output.append((q, rq))
        output.append((r, rr))
    output.append((pairs[-1][0].copy(), float(pairs[-1][1])))
    return output


def _uniform_resample(pairs, count):
    count = max(2, int(count))
    if len(pairs) < 2:
        return pairs
    return [_sample_pair(pairs, index / max(count - 1, 1))[:2] for index in range(count)]


def _target_count(pairs, branch, settings):
    level = min(max(int(branch.get("level", 0)), 0), 2)
    lod = str(getattr(settings, "lod", "LOD0"))
    spacing_table = _LOD_SPACING.get(lod, _LOD_SPACING["LOD0"])
    max_table = _MAX_POINTS.get(lod, _MAX_POINTS["LOD0"])
    _cumulative, length = _polyline_lengths(pairs)
    height = max(float(getattr(settings, "height", 10.0)), 0.25)

    spacing = max(height * float(spacing_table[level]), 0.11)
    desired = int(math.ceil(length / spacing)) + 1

    # Relay axes deserve extra axial resolution because they carry the visual
    # continuation of the trunk.  Ordinary secondaries only receive extra rings
    # when they are part of the explicit structural willow architecture.
    if branch.get("willow_relay_axis", False):
        desired = max(desired, 22 if lod == "LOD0" else 16)
    if level == 2 and not (
        branch.get("willow_relay_scaffold", False)
        or branch.get("willow_structural_fork", False)
        or branch.get("willow_scaffold_fill", False)
    ):
        desired = min(desired, max(len(pairs), 10 if lod == "LOD0" else 8))

    return max(len(pairs), min(int(max_table[level]), desired))


def _curve_strength(branch):
    level = int(branch.get("level", 0))
    if branch.get("willow_root_buttress", False):
        return 0.032, 0.70, 0.0
    if level <= 0:
        return 0.036, 0.72, 0.42
    if branch.get("willow_relay_axis", False):
        return 0.052, 1.05, 0.54
    if level == 1:
        return 0.050, 1.12, 0.58
    if level == 2 and (
        branch.get("willow_relay_scaffold", False)
        or branch.get("willow_structural_fork", False)
        or branch.get("willow_scaffold_fill", False)
    ):
        return 0.034, 1.42, 0.48
    return 0.018, 1.65, 0.34


def _sinuous_offset(pairs, branch, settings):
    if len(pairs) < 4:
        return pairs

    cumulative, total_length = _polyline_lengths(pairs)
    if total_length <= 1.0e-7:
        return pairs

    branch_id = int(branch.get("id", 0))
    seed = int(getattr(settings, "seed", 1)) ^ (branch_id * 0x27D4EB2D)
    amplitude_ratio, base_cycles, depth_ratio = _curve_strength(branch)

    # Slight deterministic variation prevents all scaffolds from having the same
    # wavelength while keeping the curve broad enough to read as mature wood.
    amplitude = total_length * amplitude_ratio * (0.82 + 0.36 * _hash_unit(seed, 19))
    cycles = base_cycles * (0.82 + 0.40 * _hash_unit(seed, 43))
    phase_a = math.tau * _hash_unit(seed, 71)
    phase_b = math.tau * _hash_unit(seed, 97)

    chord = _safe_normalized(pairs[-1][0] - pairs[0][0], _WORLD_UP)
    side, up = generator._basis(chord)

    # Buttress roots should meander across the ground rather than oscillating up
    # and down.  For branches, a second lower-amplitude axis makes the S-curve
    # genuinely three-dimensional instead of planar.
    root = branch.get("willow_root_buttress", False)
    if root:
        horizontal = Vector((side.x, side.y, 0.0))
        if horizontal.length_squared <= 1.0e-8:
            horizontal = Vector((-chord.y, chord.x, 0.0))
        side = _safe_normalized(horizontal, Vector((1.0, 0.0, 0.0)))
        up = Vector((0.0, 0.0, 0.0))

    output = []
    for index, (point, radius) in enumerate(pairs):
        t = cumulative[index] / total_length
        # Lock the actual junction and gradually release the curve over the first
        # ~12% of the branch.  Unlike a symmetric endpoint envelope, the tip is
        # free to wander and therefore does not straighten itself near the end.
        gate = _smoothstep(0.0, 0.12, t)
        body = 0.72 + 0.28 * math.sin(math.pi * _clamp(t))

        wave_a = math.sin(math.tau * cycles * t + phase_a)
        # Different irrational-ish wavelength and phase makes a slow spatial
        # corkscrew/meander without looking like a literal sine wave.
        wave_b = math.sin(math.tau * (cycles * 0.63 + 0.17) * t + phase_b)
        offset = side * (wave_a * amplitude * gate * body)
        offset += up * (wave_b * amplitude * depth_ratio * gate * body)
        output.append((point + offset, float(radius)))

    output[0] = (pairs[0][0].copy(), float(pairs[0][1]))
    return output


def _fair_branch(pairs, branch, settings):
    if len(pairs) < 3:
        return pairs
    level = int(branch.get("level", 0))
    target = _target_count(pairs, branch, settings)

    # Major wood receives two endpoint-preserving corner-cutting passes.  Fine
    # structural secondaries get one; ordinary fine twigs stay almost untouched.
    passes = 2 if level <= 1 else 1
    if level >= 3:
        passes = 0
    working = [(p.copy(), float(r)) for p, r in pairs]
    for _ in range(passes):
        working = _chaikin_once(working)
    working = _uniform_resample(working, target)
    working = _sinuous_offset(working, branch, settings)

    # One last mild fairing pass blends the meander into the already-smoothed
    # centerline.  Re-resample afterward to retain a predictable ring count.
    if level <= 2 and len(working) >= 5:
        working = _chaikin_once(working)
        working = _uniform_resample(working, target)
    working[0] = (pairs[0][0].copy(), float(pairs[0][1]))
    return working


def _transform_child_to_parent(child_pairs, old_parent, new_parent):
    if not child_pairs or len(old_parent) < 2 or len(new_parent) < 2:
        return [(p.copy(), float(r)) for p, r in child_pairs]

    old_start = child_pairs[0][0]
    factor = _closest_factor(old_parent, old_start)
    _old_attach, _old_radius, old_tangent = _sample_pair(old_parent, factor)
    new_attach, _new_radius, new_tangent = _sample_pair(new_parent, factor)
    try:
        rotation = old_tangent.rotation_difference(new_tangent)
    except Exception:
        rotation = None

    output = []
    for point, radius in child_pairs:
        offset = point - old_start
        if rotation is not None:
            offset = rotation @ offset
        output.append((new_attach + offset, float(radius)))
    output[0] = (new_attach.copy(), float(child_pairs[0][1]))
    return output


def _process_hierarchy(branches, settings):
    if not branches:
        return branches

    original = {int(branch.get("id", index)): _pairs(branch) for index, branch in enumerate(branches)}
    by_id = {int(branch.get("id", index)): branch for index, branch in enumerate(branches)}
    children = {}
    roots = []
    for branch in branches:
        branch_id = int(branch.get("id", 0))
        parent_id = int(branch.get("parent_id", -1))
        if parent_id in by_id:
            children.setdefault(parent_id, []).append(branch_id)
        else:
            roots.append(branch_id)

    processed = {}

    def visit(branch_id):
        if branch_id in processed:
            return
        branch = by_id[branch_id]
        parent_id = int(branch.get("parent_id", -1))
        working = [(p.copy(), float(r)) for p, r in original.get(branch_id, ())]
        if parent_id in by_id:
            if parent_id not in processed:
                visit(parent_id)
            working = _transform_child_to_parent(working, original[parent_id], processed[parent_id])

        # Skip expensive extra sampling on ordinary fine twigs; their existing
        # structural-motion path already contains sufficient detail at card scale.
        level = int(branch.get("level", 0))
        structural = level <= 1 or branch.get("willow_root_buttress", False) or branch.get("willow_relay_scaffold", False) or branch.get("willow_structural_fork", False) or branch.get("willow_scaffold_fill", False)
        if structural:
            working = _fair_branch(working, branch, settings)

        processed[branch_id] = working
        branch["points"] = [(p.copy(), float(r)) for p, r in working]
        branch["length"] = generator._polyline_length(branch)
        branch["willow_sinuous_geometry"] = True
        branch["willow_sinuous_version"] = 1
        branch["willow_axial_samples"] = len(working)

        for child_id in children.get(branch_id, ()):
            visit(child_id)

    for root_id in roots:
        visit(root_id)
    for branch_id in by_id:
        visit(branch_id)

    return branches


def _generate_with_sinuous_geometry(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW":
        return branches, terminals
    _process_hierarchy(branches, settings)
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_sinuous_geometry
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
