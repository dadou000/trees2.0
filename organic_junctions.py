"""Organic parent/child junction preprocessing.

Exact Boolean union removes overlapping interior faces, but it cannot make two
poorly-shaped tubes look like one piece of growing wood.  The old generator also
used a large first-ring collar followed by an abrupt radius drop, which produces
the wedge/bulb transitions visible on large willow forks.

This final skeleton wrapper improves the actual branch graph before meshing:

* child centerlines leave the parent through a short C1-like cubic transition;
* exact-Boolean branches use a reduced, smoothly-decaying root collar;
* parent radii receive a bounded local flare around substantial child inserts;
* all edits happen on the procedural branch dictionaries, so foliage mapping and
  game-runtime branch metadata remain consistent with the visible wood.

There is no voxel remesh and no global topology operation here.
"""

import math

import bpy
from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _smoothstep01(value):
    t = _clamp(value)
    return t * t * (3.0 - 2.0 * t)


def _safe_normalized(vector, fallback):
    if vector.length_squared <= 1.0e-12:
        return fallback.copy()
    return vector.normalized()


def _lod_index(lod):
    try:
        return int(str(lod).replace("LOD", ""))
    except Exception:
        return 0


def _advanced_settings():
    scene = getattr(bpy.context, "scene", None)
    return getattr(scene, "trees2_advanced_settings", None) if scene else None


def _lengths(branch):
    points = branch.get("points", ())
    cumulative = [0.0]
    total = 0.0
    for index in range(len(points) - 1):
        total += (points[index + 1][0] - points[index][0]).length
        cumulative.append(total)
    return cumulative, total


def _closest_parent_frame(parent, target):
    points = parent.get("points", ())
    if len(points) < 2:
        return 0.0, target.copy(), Vector((0.0, 0.0, 1.0))

    cumulative, total = _lengths(parent)
    if total <= 1.0e-9:
        direction = _safe_normalized(points[1][0] - points[0][0], Vector((0.0, 0.0, 1.0)))
        return 0.0, points[0][0].copy(), direction

    best_distance = float("inf")
    best_length = 0.0
    best_point = points[0][0].copy()
    best_tangent = Vector((0.0, 0.0, 1.0))

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
            segment_length = math.sqrt(length_sq)
            best_length = cumulative[index] + segment_length * local
            best_point = projected
            best_tangent = delta / segment_length

    return _clamp(best_length / total), best_point, best_tangent


def _bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    return (
        p0 * (u * u * u)
        + p1 * (3.0 * u * u * t)
        + p2 * (3.0 * u * t * t)
        + p3 * (t * t * t)
    )


def _fair_child_root(branch, parent, settings, exact_boolean):
    points = branch.get("points", ())
    if len(points) < 3 or not parent:
        return False
    if branch.get("willow_root_buttress", False):
        return False

    level = max(1, int(branch.get("level", 1)))
    blend_ratio = {1: 0.16, 2: 0.135, 3: 0.10, 4: 0.075}.get(level, 0.075)
    if _lod_index(settings.lod) >= 2:
        blend_ratio *= 0.72

    cumulative, total = _lengths(branch)
    if total <= 1.0e-6:
        return False

    target_length = max(
        total * blend_ratio,
        min(total * 0.24, float(settings.base_radius) * (0.34 if level == 1 else 0.22)),
    )
    target_length = min(target_length, total * 0.24)

    end_index = 1
    while end_index < len(cumulative) - 1 and cumulative[end_index] < target_length:
        end_index += 1
    end_index = max(2, min(end_index, len(points) - 1))
    if end_index >= len(points):
        return False

    p0 = points[0][0].copy()
    p3 = points[end_index][0].copy()
    chord = p3 - p0
    chord_length = chord.length
    if chord_length <= 1.0e-5:
        return False

    child_initial = _safe_normalized(points[1][0] - p0, chord.normalized())
    _parent_factor, _attach_point, parent_tangent = _closest_parent_frame(parent, p0)
    downstream_index = min(len(points) - 1, end_index + 1)
    downstream = _safe_normalized(
        points[downstream_index][0] - points[max(0, end_index - 1)][0],
        child_initial,
    )

    # A real branch base does not instantly form the full branch angle at one
    # ring.  Keep most of the child's intended direction while borrowing a
    # little parent tangent to make the wood visually flow through the fork.
    parent_influence = 0.20 if level == 1 else 0.14
    start_direction = _safe_normalized(
        child_initial * (1.0 - parent_influence) + parent_tangent * parent_influence,
        child_initial,
    )
    if start_direction.dot(child_initial) < 0.45:
        start_direction = child_initial

    p1 = p0 + start_direction * (chord_length * 0.34)
    p2 = p3 - downstream * (chord_length * 0.30)

    old_points = list(points)
    new_points = list(points)

    collar = max(0.0, float(getattr(settings, "branch_collar", 0.0)))
    original_root_radius = float(points[0][1])
    if collar > 1.0e-6:
        core_radius = original_root_radius / (1.0 + collar)
    else:
        core_radius = original_root_radius

    # The large collar is useful only for intersecting-tube fallback geometry.
    # Exact Boolean already fuses the solids, so keep only a subtle anatomical
    # swelling and let the parent flare carry the junction mass.
    if exact_boolean:
        effective_collar = min(0.16, collar * 0.34)
    else:
        effective_collar = min(collar, 0.34)
    root_radius = core_radius * (1.0 + effective_collar)
    end_radius = float(points[end_index][1])

    for index in range(end_index + 1):
        t = cumulative[index] / max(cumulative[end_index], 1.0e-6)
        eased = _smoothstep01(t)
        if 0 < index < end_index:
            position = _bezier(p0, p1, p2, p3, t)
        else:
            position = points[index][0].copy()

        target_radius = root_radius * (1.0 - eased) + end_radius * eased
        # Keep a small amount of the original taper character, but remove the
        # first-ring cliff caused by collar multiplication.
        radius = target_radius * 0.84 + float(old_points[index][1]) * 0.16
        new_points[index] = (position, max(radius, end_radius * 0.88))

    branch["points"] = new_points
    branch["length"] = generator._polyline_length(branch)
    branch["trees2_organic_root_blend"] = True
    branch["trees2_organic_root_blend_fraction"] = float(
        cumulative[end_index] / max(total, 1.0e-6)
    )
    return True


def _apply_parent_flares(branches, settings):
    by_id = {int(branch.get("id", index)): branch for index, branch in enumerate(branches)}
    contributions = {branch_id: [0.0] * len(branch.get("points", ())) for branch_id, branch in by_id.items()}
    flare_count = 0

    for child in branches:
        parent_id = int(child.get("parent_id", -1))
        parent = by_id.get(parent_id)
        child_points = child.get("points", ())
        if parent is None or len(parent.get("points", ())) < 2 or not child_points:
            continue
        if child.get("willow_root_buttress", False):
            continue

        parent_cumulative, parent_total = _lengths(parent)
        if parent_total <= 1.0e-6:
            continue
        attach_factor, _point, _tangent = _closest_parent_frame(parent, child_points[0][0])
        attach_length = attach_factor * parent_total
        child_radius = max(float(child_points[0][1]), 1.0e-5)
        influence = min(
            parent_total * 0.14,
            max(child_radius * 2.8, float(settings.base_radius) * 0.075),
        )
        if influence <= 1.0e-6:
            continue

        level = int(child.get("level", 1))
        amplitude_scale = 0.20 if level <= 1 else (0.15 if level == 2 else 0.09)
        for index, arc_length in enumerate(parent_cumulative):
            distance = abs(arc_length - attach_length)
            if distance >= influence:
                continue
            t = 1.0 - distance / influence
            weight = _smoothstep01(t)
            local_radius = float(parent["points"][index][1])
            amplitude = min(child_radius * amplitude_scale, local_radius * 0.14)
            contributions[parent_id][index] += amplitude * weight
        flare_count += 1

    for parent_id, values in contributions.items():
        parent = by_id[parent_id]
        if not values or not parent.get("points"):
            continue
        new_points = []
        for index, (point, radius) in enumerate(parent["points"]):
            # Multiple children may overlap spatially; cap total swelling so a
            # cluster of forks does not turn the parent into a knot/blob.
            addition = min(values[index], float(radius) * 0.20)
            new_points.append((point.copy(), float(radius) + addition))
        parent["points"] = new_points

    return flare_count


def _generate_with_organic_junctions(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if not branches:
        return branches, terminals

    advanced = _advanced_settings()
    exact_boolean = bool(advanced and advanced.junction_mode == "EXACT_BOOLEAN")
    by_id = {int(branch.get("id", index)): branch for index, branch in enumerate(branches)}

    blended = 0
    for branch in sorted(branches, key=lambda item: (int(item.get("level", 0)), int(item.get("id", 0)))):
        if int(branch.get("level", 0)) <= 0:
            continue
        parent = by_id.get(int(branch.get("parent_id", -1)))
        if _fair_child_root(branch, parent, settings, exact_boolean):
            blended += 1

    flares = _apply_parent_flares(branches, settings)

    try:
        trunk = min(branches, key=lambda item: (int(item.get("level", 0)), int(item.get("id", 0))))
        trunk["trees2_organic_junction_version"] = 1
        trunk["trees2_organic_blended_roots"] = int(blended)
        trunk["trees2_organic_parent_flares"] = int(flares)
    except Exception:
        pass

    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_organic_junctions
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
