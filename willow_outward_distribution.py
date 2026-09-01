"""Outward-biased structural distribution for mature weeping willow.

This stage sits between willow relay topology and hierarchy-aware structural
motion.  It addresses a failure mode of the generic recursive growth pass:
short generic laterals accumulate close to the central axes, while many of the
leaf-bearing terminals are therefore also selected close to the core.  The
result reads as a spiderweb/lightning skeleton with hanging foliage starting too
far inward.

For WILLOW only this module:
* gives useful major scaffolds a modest distal/outward continuation;
* keeps explicit botanical/architectural branches, but ranks generic children
  and removes weak proximal clutter with their complete subtrees;
* rebuilds the real terminal set from the retained topology;
* gives outer terminals full curtain authority, mid terminals a reduced budget,
  and retains only a small amount of short inner fill so the crown does not
  become hollow.

The later willow_structure_motion and willow_sinuous_geometry stages then bend
and fair this cleaner hierarchy, so this module deliberately avoids introducing
high-frequency shape noise itself.
"""

import math

from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False
_WORLD_DOWN = Vector((0.0, 0.0, -1.0))


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


def _stable_unit(seed, value):
    x = (int(value) ^ int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
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


def _branch_length(branch):
    pairs = branch.get("points", ())
    if len(pairs) < 2:
        return 0.0
    return sum((pairs[index + 1][0] - pairs[index][0]).length for index in range(len(pairs) - 1))


def _sample_point(branch, factor):
    if len(branch.get("points", ())) < 2:
        points = branch.get("points", ())
        return points[0][0].copy() if points else Vector((0.0, 0.0, 0.0))
    point, _radius, _tangent = generator._point_on_polyline(branch, _clamp(factor))
    return point


def _closest_factor(parent, target):
    pairs = parent.get("points", ())
    if len(pairs) < 2:
        return 0.0

    cumulative = [0.0]
    total = 0.0
    for index in range(len(pairs) - 1):
        total += (pairs[index + 1][0] - pairs[index][0]).length
        cumulative.append(total)
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
            segment_length = 0.0
        else:
            local = _clamp((target - a).dot(delta) / length_sq)
            projection = a + delta * local
            segment_length = math.sqrt(length_sq)
        distance = (target - projection).length_squared
        if distance < best_distance:
            best_distance = distance
            best_length = cumulative[index] + segment_length * local
    return _clamp(best_length / total)


def _origin(branches):
    for branch in branches:
        if int(branch.get("level", 0)) == 0 and branch.get("points"):
            return branch["points"][0][0].copy()
    for branch in branches:
        if branch.get("points"):
            return branch["points"][0][0].copy()
    return Vector((0.0, 0.0, 0.0))


def _radial(point, origin):
    delta = point - origin
    return math.hypot(float(delta.x), float(delta.y))


def _branch_exposure(branch, origin):
    values = []
    for factor in (0.52, 0.70, 0.86, 1.0):
        point = branch["points"][-1][0] if factor >= 0.999 else _sample_point(branch, factor)
        values.append(_radial(point, origin))
    return max(values) if values else 0.0


def _crown_radius_reference(branches, origin, settings):
    samples = []
    for branch in branches:
        if (
            branch.get("dead", False)
            or branch.get("willow_root_buttress", False)
            or int(branch.get("level", 0)) < 1
            or len(branch.get("points", ())) < 2
        ):
            continue
        samples.append(_branch_exposure(branch, origin))
    if not samples:
        return max(float(settings.branch_length), float(settings.base_radius) * 4.0, 1.0)
    samples.sort()
    # A robust outer-shell reference.  Using P90 prevents one extreme scaffold
    # from making all otherwise useful terminals appear artificially central.
    index = min(len(samples) - 1, max(0, int(round((len(samples) - 1) * 0.90))))
    return max(samples[index], float(settings.base_radius) * 4.0, 1.0e-4)


def _is_explicit_structure(branch):
    if int(branch.get("level", 0)) <= 0:
        return True
    return bool(
        branch.get("willow_relay_axis", False)
        or branch.get("willow_relay_scaffold", False)
        or branch.get("willow_structural_fork", False)
        or branch.get("willow_scaffold_fill", False)
        or branch.get("willow_root_buttress", False)
        or branch.get("willow_codominant", False)
    )


def _major_scaffold(branch):
    level = int(branch.get("level", 0))
    if branch.get("willow_root_buttress", False):
        return False
    if branch.get("willow_relay_axis", False):
        # Relay axes carry height.  Keep them mostly upright; their laterals are
        # the structures that should occupy the outer crown.
        return False
    if level == 1:
        return True
    return bool(
        level == 2
        and (
            branch.get("willow_relay_scaffold", False)
            or branch.get("willow_structural_fork", False)
            or branch.get("willow_scaffold_fill", False)
        )
    )


def _extend_major_scaffold(branch, origin, crown_radius, settings):
    """Continue useful structural wood outward before the sinuous pass bends it."""
    if not _major_scaffold(branch) or len(branch.get("points", ())) < 2:
        return False

    pairs = _pairs(branch)
    start = pairs[0][0]
    end = pairs[-1][0]
    tangent = _safe_normalized(end - pairs[-2][0], Vector((1.0, 0.0, 0.0)))
    radial = Vector((end.x - origin.x, end.y - origin.y, 0.0))
    if radial.length_squared <= 1.0e-10:
        radial = Vector((tangent.x, tangent.y, 0.0))
    radial = _safe_normalized(radial, Vector((1.0, 0.0, 0.0)))

    start_exposure = _radial(start, origin) / max(crown_radius, 1.0e-5)
    end_exposure = _radial(end, origin) / max(crown_radius, 1.0e-5)
    gain = end_exposure - start_exposure
    level = int(branch.get("level", 1))

    target_exposure = 0.72 if level <= 1 else 0.66
    if end_exposure >= target_exposure and gain >= 0.20:
        return False

    length = max(_branch_length(branch), float(settings.base_radius) * 0.25)
    height = max(float(settings.height), 1.0)
    missing = max(0.0, target_exposure - end_exposure) * crown_radius
    extra = min(
        max(length * (0.10 if level <= 1 else 0.07), missing * 0.72),
        height * (0.16 if level <= 1 else 0.10),
    )
    if extra <= max(float(settings.base_radius) * 0.08, 0.10):
        return False

    # Preserve the current tangent at the join, then progressively bias the new
    # growth outward.  The later structural-motion/sinuous stages make the path
    # botanical; this only supplies the missing distal occupation.
    guide = _safe_normalized(tangent * 0.62 + radial * 0.78 + _WORLD_DOWN * 0.05, tangent)
    steps = 4 if level <= 1 else 3
    tip_radius = float(pairs[-1][1])
    current = end.copy()
    new_pairs = list(pairs)

    for index in range(1, steps + 1):
        t = index / steps
        direction = _safe_normalized(
            tangent.lerp(guide, _smoothstep(0.0, 1.0, t)),
            guide,
        )
        current = current + direction * (extra / steps)
        radius = max(
            tip_radius * (1.0 - 0.50 * t),
            float(settings.base_radius) * (0.006 if level <= 1 else 0.0045),
        )
        new_pairs.append((current.copy(), radius))

    branch["points"] = new_pairs
    branch["length"] = generator._polyline_length(branch)
    branch["willow_outward_extended"] = True
    return True


def _child_score(child, parent, origin, crown_radius, settings):
    if len(child.get("points", ())) < 2:
        return -10.0

    start = child["points"][0][0]
    end = child["points"][-1][0]
    attach = _closest_factor(parent, start)
    start_r = _radial(start, origin) / max(crown_radius, 1.0e-5)
    end_r = _branch_exposure(child, origin) / max(crown_radius, 1.0e-5)
    radial_gain = end_r - start_r
    length_norm = _branch_length(child) / max(float(settings.height), 1.0e-5)

    # The score deliberately rewards distal attachment and shell occupation more
    # than sheer branch count.  This removes the short recursive lightning-like
    # splits close to the parent origin while retaining useful outward laterals.
    score = 0.0
    score += _smoothstep(0.34, 0.82, attach) * 1.70
    score += _smoothstep(0.18, 0.78, end_r) * 1.55
    score += _smoothstep(-0.02, 0.22, radial_gain) * 1.35
    score += _smoothstep(0.025, 0.16, length_norm) * 0.70

    if attach < 0.30:
        score -= 1.20
    elif attach < 0.43:
        score -= 0.45
    if end_r < 0.24:
        score -= 0.90
    if radial_gain < -0.03:
        score -= 0.70
    if child.get("dead", False):
        score -= 0.35
    return score


def _generic_child_limit(parent, lod):
    level = int(parent.get("level", 0))
    lod_scale = {
        "LOD0": 1.00,
        "LOD1": 0.90,
        "LOD2": 0.72,
        "LOD3": 0.55,
        "LOD4": 0.42,
    }.get(str(lod), 1.0)

    if parent.get("willow_relay_axis", False):
        base = 4
    elif level <= 0:
        base = 3
    elif level == 1:
        base = 3
    elif level == 2:
        base = 2
    else:
        base = 1
    return max(1, round(base * lod_scale))


def _filter_core_clutter(branches, settings, origin, crown_radius):
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

    keep = set()
    pruned_roots = 0

    def visit(branch_id):
        nonlocal pruned_roots
        if branch_id in keep or branch_id not in by_id:
            return
        keep.add(branch_id)
        parent = by_id[branch_id]
        child_ids = children.get(branch_id, ())
        explicit = []
        ranked = []

        for child_id in child_ids:
            child = by_id[child_id]
            if _is_explicit_structure(child):
                explicit.append(child_id)
            else:
                ranked.append((_child_score(child, parent, origin, crown_radius, settings), child_id))

        for child_id in explicit:
            visit(child_id)

        ranked.sort(key=lambda item: item[0], reverse=True)
        limit = _generic_child_limit(parent, settings.lod)
        accepted = 0
        for score, child_id in ranked:
            if accepted >= limit:
                pruned_roots += 1
                continue
            # Let a very good child survive regardless; increasingly reject the
            # short/proximal tail that creates the webby core.
            threshold = 0.90 if int(parent.get("level", 0)) <= 1 else 1.05
            if score < threshold:
                pruned_roots += 1
                continue
            visit(child_id)
            accepted += 1

    for root_id in roots:
        visit(root_id)

    filtered = [branch for branch in branches if int(branch.get("id", -1)) in keep]
    return filtered, pruned_roots


def _children_map(branches):
    ids = {int(branch.get("id", -1)) for branch in branches}
    children = {}
    for branch in branches:
        parent_id = int(branch.get("parent_id", -1))
        if parent_id in ids:
            children.setdefault(parent_id, []).append(int(branch.get("id", -1)))
    return children


def _terminal_score(branch, origin, crown_radius, settings):
    start = branch["points"][0][0]
    end = branch["points"][-1][0]
    start_r = _radial(start, origin) / max(crown_radius, 1.0e-5)
    exposure = _branch_exposure(branch, origin) / max(crown_radius, 1.0e-5)
    radial_gain = exposure - start_r
    length_norm = _branch_length(branch) / max(float(settings.height), 1.0e-5)
    h = max(float(start.z), float(end.z)) / max(float(settings.height), 1.0e-5)

    score = (
        exposure * 1.70
        + _clamp(radial_gain, -0.25, 0.45) * 1.65
        + _smoothstep(0.025, 0.14, length_norm) * 0.42
        + _smoothstep(0.24, 0.70, h) * 0.18
    )
    return score, _clamp(exposure), radial_gain


def _rebuild_terminals(branches, settings, origin, crown_radius):
    children = _children_map(branches)
    outer = []
    middle = []
    inner = []

    for branch in branches:
        branch_id = int(branch.get("id", -1))
        if (
            children.get(branch_id)
            or int(branch.get("level", 0)) <= 0
            or branch.get("dead", False)
            or branch.get("willow_no_foliage", False)
            or branch.get("willow_root_buttress", False)
            or len(branch.get("points", ())) < 2
        ):
            continue

        score, exposure, radial_gain = _terminal_score(branch, origin, crown_radius, settings)
        branch["willow_terminal_exposure"] = float(exposure)

        if exposure >= 0.54 or radial_gain >= 0.18:
            outer.append((score, branch))
        elif exposure >= 0.34 or radial_gain >= 0.08:
            middle.append((score, branch))
        else:
            inner.append((score, branch))

    outer.sort(key=lambda item: item[0], reverse=True)
    middle.sort(key=lambda item: item[0], reverse=True)
    inner.sort(key=lambda item: item[0], reverse=True)

    result = []
    for _score, branch in outer:
        exposure = float(branch.get("willow_terminal_exposure", 0.70))
        branch["willow_terminal_weight"] = 0.96 + 0.16 * _smoothstep(0.54, 0.95, exposure)
        branch["willow_terminal_length_scale"] = 0.94 + 0.14 * _smoothstep(0.54, 0.95, exposure)
        branch["willow_terminal_fill_only"] = False
        result.append(branch)

    for _score, branch in middle:
        exposure = float(branch.get("willow_terminal_exposure", 0.42))
        branch["willow_terminal_weight"] = 0.62 + 0.22 * _smoothstep(0.34, 0.62, exposure)
        branch["willow_terminal_length_scale"] = 0.70 + 0.18 * _smoothstep(0.34, 0.62, exposure)
        branch["willow_terminal_fill_only"] = False
        result.append(branch)

    # Keep just enough inner growth to maintain a dark volumetric core.  These
    # terminals are explicitly short/fill-only, so they cannot recreate the old
    # floor-length central mop.
    inner_budget = max(5, min(len(inner), round((len(outer) + len(middle)) * 0.11)))
    for _score, branch in inner[:inner_budget]:
        branch["willow_terminal_weight"] = 0.34
        branch["willow_terminal_length_scale"] = 0.52
        branch["willow_terminal_fill_only"] = True
        result.append(branch)

    return result, len(outer), len(middle), inner_budget


def _generate_outward(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    branches = list(branches)
    origin = _origin(branches)
    crown_radius = _crown_radius_reference(branches, origin, settings)

    extended = 0
    for branch in branches:
        if _extend_major_scaffold(branch, origin, crown_radius, settings):
            extended += 1

    # Re-evaluate the radius after scaffold continuation before scoring generic
    # children and terminal exposure.
    crown_radius = _crown_radius_reference(branches, origin, settings)
    branches, pruned_roots = _filter_core_clutter(branches, settings, origin, crown_radius)
    crown_radius = _crown_radius_reference(branches, origin, settings)
    terminals, outer_count, middle_count, inner_count = _rebuild_terminals(
        branches, settings, origin, crown_radius
    )

    try:
        trunk = next(branch for branch in branches if int(branch.get("level", 0)) == 0)
        trunk["willow_outward_distribution_version"] = 1
        trunk["willow_outward_crown_radius"] = float(crown_radius)
        trunk["willow_outward_extended_scaffolds"] = int(extended)
        trunk["willow_outward_pruned_subtree_roots"] = int(pruned_roots)
        trunk["willow_outward_outer_terminals"] = int(outer_count)
        trunk["willow_outward_middle_terminals"] = int(middle_count)
        trunk["willow_outward_inner_fill_terminals"] = int(inner_count)
    except Exception:
        pass

    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_outward
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
