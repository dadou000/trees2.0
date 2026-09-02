"""Final viability rules for willow structural terminals.

A mature living branch that carries substantial diameter should either continue
far enough to support a useful crown sector or divide into descendants.  A thick
50 cm limb that simply stops with nothing on it is therefore treated as a graph
failure, not normal random variation.

This post-balance wrapper runs before foliage-anchor scoring and enforces that
visual invariant without adding new branch IDs:

* thick living childless branches that can carry foliage are extended into a
  curved/tapered distal support;
* intentionally non-foliated or dead childless stubs are demoted to subordinate
  diameter instead of remaining massive clubs;
* relay axes are never demoted by this pass;
* existing terminal dictionaries remain valid because branches are edited in
  place and no IDs are added or removed.
"""

import math

from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False
_WORLD_DOWN = Vector((0.0, 0.0, -1.0))


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _safe_normalized(vector, fallback):
    if vector.length_squared <= 1.0e-12:
        return fallback.copy()
    return vector.normalized()


def _stable_unit(seed, branch_id, salt):
    value = (int(seed) ^ (int(branch_id) * 0x9E3779B1) ^ int(salt)) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value / 4294967296.0


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


def _closest_parent_radius(parent, target):
    points = parent.get("points", ())
    if len(points) < 2:
        return float(points[0][1]) if points else 0.0

    best_distance = float("inf")
    best_radius = float(points[0][1])
    for index in range(len(points) - 1):
        a, ar = points[index]
        b, br = points[index + 1]
        delta = b - a
        length_sq = delta.length_squared
        if length_sq <= 1.0e-12:
            continue
        local = _clamp((target - a).dot(delta) / length_sq)
        projected = a + delta * local
        distance = (target - projected).length_squared
        if distance < best_distance:
            best_distance = distance
            best_radius = float(ar) + (float(br) - float(ar)) * local
    return best_radius


def _root_core_radius(branch, settings):
    points = branch.get("points", ())
    if not points:
        return 0.0
    r0 = float(points[0][1])
    if len(points) < 2:
        return r0
    r1 = float(points[1][1])
    collar = max(0.0, float(getattr(settings, "branch_collar", 0.0)))
    decol = r0 / max(1.0 + collar, 1.0)
    return max(1.0e-6, min(r0, max(r1 * 1.08, decol)))


def _tree_origin(branches):
    for branch in branches:
        if int(branch.get("level", 0)) == 0 and branch.get("points"):
            return branch["points"][0][0].copy()
    return Vector((0.0, 0.0, 0.0))


def _demote_stub(branch, parent_radius, settings):
    points = branch.get("points", ())
    if not points:
        return False
    core = _root_core_radius(branch, settings)
    target = min(
        parent_radius * 0.24 if parent_radius > 1.0e-6 else core,
        float(settings.base_radius) * 0.055,
    )
    target = max(target, float(settings.base_radius) * 0.012)
    if core <= target * 1.02:
        return False

    scale = target / max(core, 1.0e-6)
    new_points = []
    count = max(1, len(points) - 1)
    for index, (point, radius) in enumerate(points):
        t = index / count
        # Stronger taper toward the end keeps the stub anatomically subordinate.
        taper = 1.0 - 0.58 * (t ** 1.35)
        new_points.append((point.copy(), max(float(settings.base_radius) * 0.006, float(radius) * scale * taper)))
    branch["points"] = new_points
    branch["length"] = generator._polyline_length(branch)
    branch["willow_viability_demoted_stub"] = True
    branch["willow_viability_radius_scale"] = float(scale)
    return True


def _extend_terminal(branch, origin, settings):
    points = branch.get("points", ())
    if len(points) < 2:
        return False

    root_radius = _root_core_radius(branch, settings)
    current_length = max(_branch_length(branch), 1.0e-6)
    level = int(branch.get("level", 1))
    height = max(float(settings.height), 1.0)

    # Thick wood should have enough run to read as a structural support.  Use a
    # slenderness rule plus a small fraction of tree height, then cap it so this
    # pass cannot invent giant new scaffolds.
    diameter_rule = root_radius * (10.0 if level <= 2 else 8.0)
    height_rule = height * (0.085 if level <= 2 else 0.055)
    target_length = max(diameter_rule, height_rule)
    target_length = min(target_length, height * (0.24 if level <= 2 else 0.14))
    if current_length >= target_length * 0.92:
        return False

    extra = target_length - current_length
    if extra <= max(0.12, float(settings.base_radius) * 0.15):
        return False

    end = points[-1][0].copy()
    tangent = _safe_normalized(points[-1][0] - points[-2][0], Vector((1.0, 0.0, 0.0)))
    radial = Vector((end.x - origin.x, end.y - origin.y, 0.0))
    if radial.length_squared <= 1.0e-10:
        radial = Vector((tangent.x, tangent.y, 0.0))
    radial = _safe_normalized(radial, Vector((1.0, 0.0, 0.0)))

    side = _safe_normalized(tangent.cross(Vector((0.0, 0.0, 1.0))), Vector((0.0, 1.0, 0.0)))
    branch_id = int(branch.get("id", 0))
    side_sign = -1.0 if _stable_unit(settings.seed, branch_id, 0xA17) < 0.5 else 1.0
    waviness = 0.08 + 0.06 * _stable_unit(settings.seed, branch_id, 0xB31)

    steps = 5 if level <= 2 else 4
    tip_radius_start = float(points[-1][1])
    minimum_tip = float(settings.base_radius) * (0.005 if level <= 2 else 0.0035)
    new_points = list(points)
    current = end.copy()

    for index in range(1, steps + 1):
        t = index / steps
        outward = radial * (0.52 + 0.20 * t)
        continuation = tangent * (0.72 - 0.18 * t)
        gravity = _WORLD_DOWN * (0.05 + 0.20 * (t ** 1.5))
        meander = side * side_sign * math.sin(t * math.pi * 1.35) * waviness
        direction = _safe_normalized(continuation + outward + gravity + meander, tangent)
        current = current + direction * (extra / steps)
        radius = max(
            minimum_tip,
            tip_radius_start * ((1.0 - t) ** 1.18) * 0.92,
        )
        new_points.append((current.copy(), radius))

    branch["points"] = new_points
    branch["length"] = generator._polyline_length(branch)
    branch["willow_viability_extended"] = True
    branch["willow_viability_original_length"] = float(current_length)
    branch["willow_viability_target_length"] = float(target_length)
    return True


def _generate_viable(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    branches = list(branches)
    children = _children_map(branches)
    by_id = {int(branch.get("id", -1)): branch for branch in branches}
    origin = _tree_origin(branches)
    extended = 0
    demoted = 0

    for branch in branches:
        branch_id = int(branch.get("id", -1))
        level = int(branch.get("level", 0))
        if level <= 0 or branch.get("willow_root_buttress", False):
            continue
        if children.get(branch_id):
            continue
        if branch.get("willow_relay_axis", False):
            continue
        points = branch.get("points", ())
        if len(points) < 2:
            continue

        parent = by_id.get(int(branch.get("parent_id", -1)))
        parent_radius = _closest_parent_radius(parent, points[0][0]) if parent is not None else 0.0
        root_radius = _root_core_radius(branch, settings)
        current_length = max(_branch_length(branch), 1.0e-6)

        # Only intervene when the branch is visibly structural. Fine twigs are
        # intentionally allowed to be short.
        heavy_threshold = max(
            float(settings.base_radius) * (0.060 if level <= 2 else 0.038),
            parent_radius * (0.16 if level <= 2 else 0.12),
        )
        if root_radius < heavy_threshold:
            continue

        too_short = current_length < max(root_radius * 6.5, float(settings.height) * 0.045)
        if not too_short:
            continue

        if branch.get("willow_no_foliage", False) or branch.get("dead", False):
            if _demote_stub(branch, parent_radius, settings):
                demoted += 1
        else:
            if _extend_terminal(branch, origin, settings):
                extended += 1

    try:
        trunk = min(branches, key=lambda item: (int(item.get("level", 0)), int(item.get("id", 0))))
        trunk["willow_branch_viability_version"] = 1
        trunk["willow_branch_viability_extended"] = int(extended)
        trunk["willow_branch_viability_demoted"] = int(demoted)
    except Exception:
        pass

    # Terminal references are the same dictionaries.  Extended living terminals
    # therefore receive foliage naturally in the later anchor/assembly stages.
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_viable
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
