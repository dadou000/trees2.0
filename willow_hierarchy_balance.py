"""Final hierarchy balancing for mature weeping willow structure.

Relay architecture intentionally transfers complete upper-trunk subtrees onto
new sympodial axes.  A rigid transfer preserves topology, but it also preserves
the *old trunk-scale* branch dimensions.  When the new relay is thinner this can
produce an impossible result: a lateral branch thicker/longer than the support
that carries it.  Several transferred roots can also bunch into a small portion
of the relay and make the crown read as sparse rays rather than a continuous
hierarchy.

This post-structure wrapper runs after crown spreading and before foliage-anchor
selection.  It therefore sees the final visible branch graph and enforces a few
runtime-safe invariants without changing branch IDs:

* reparented subtree geometry is scaled to the dimensions of its new support;
* child root radius is capped relative to parent radius at the true attachment;
* nearby siblings share a cross-sectional wood-area budget;
* transferred roots on a relay axis are softly redistributed along that axis;
* all child subtrees stay attached when a root is moved or geometrically scaled.

The pass is deterministic and WILLOW-only.  It does not add/remove branches, so
terminal/foliage selection remains stable and the game-runtime graph keeps the
same branch IDs.
"""

import math

from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _safe_normalized(vector, fallback):
    if vector.length_squared <= 1.0e-12:
        return fallback.copy()
    return vector.normalized()


def _children_map(branches):
    ids = {int(branch.get("id", -1)) for branch in branches}
    children = {}
    for branch in branches:
        parent_id = int(branch.get("parent_id", -1))
        if parent_id in ids:
            children.setdefault(parent_id, []).append(branch)
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


def _cumulative(branch):
    points = branch.get("points", ())
    cumulative = [0.0]
    total = 0.0
    for index in range(len(points) - 1):
        total += (points[index + 1][0] - points[index][0]).length
        cumulative.append(total)
    return cumulative, total


def _closest_frame(parent, target):
    points = parent.get("points", ())
    if len(points) < 2:
        return 0.0, target.copy(), 0.0, Vector((0.0, 0.0, 1.0))

    cumulative, total = _cumulative(parent)
    if total <= 1.0e-9:
        tangent = _safe_normalized(points[1][0] - points[0][0], Vector((0.0, 0.0, 1.0)))
        return 0.0, points[0][0].copy(), float(points[0][1]), tangent

    best_distance = float("inf")
    best_length = 0.0
    best_point = points[0][0].copy()
    best_radius = float(points[0][1])
    best_tangent = Vector((0.0, 0.0, 1.0))

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
            segment_length = math.sqrt(length_sq)
            best_distance = distance
            best_length = cumulative[index] + segment_length * local
            best_point = projected
            best_radius = float(ar) + (float(br) - float(ar)) * local
            best_tangent = delta / segment_length

    return _clamp(best_length / total), best_point, best_radius, best_tangent


def _point_frame(parent, factor):
    point, radius, tangent = generator._point_on_polyline(parent, _clamp(factor))
    return point.copy(), float(radius), tangent.copy()


def _branch_length(branch):
    return float(branch.get("length", generator._polyline_length(branch)))


def _root_core_radius(branch, settings):
    points = branch.get("points", ())
    if not points:
        return 0.0
    r0 = float(points[0][1])
    if len(points) < 2:
        return r0

    # Generated branches put the collar only on the first ring.  The second
    # sample is therefore a much better estimate of actual structural diameter.
    r1 = float(points[1][1])
    collar = max(0.0, float(getattr(settings, "branch_collar", 0.0)))
    decol = r0 / max(1.0 + collar, 1.0)
    return max(1.0e-6, min(r0, max(r1 * 1.08, decol)))


def _radius_ratio_limit(branch, parent):
    level = int(branch.get("level", 1))

    if branch.get("willow_relay_axis", False):
        # Sympodial takeover is a continuation, not an ordinary lateral.
        return 0.88
    if branch.get("willow_codominant", False):
        return 0.66
    if branch.get("willow_relay_scaffold", False):
        return 0.54 if level <= 2 else 0.44
    if branch.get("willow_structural_fork", False) or branch.get("willow_scaffold_fill", False):
        return 0.56 if level <= 2 else 0.44
    if branch.get("willow_relay_reparented", False):
        return 0.56 if level <= 2 else (0.45 if level == 3 else 0.38)
    if level <= 1:
        return 0.62
    if level == 2:
        return 0.50
    if level == 3:
        return 0.42
    return 0.35


def _length_limit(branch, parent, settings):
    level = int(branch.get("level", 1))
    parent_level = int(parent.get("level", 0))
    height = max(float(settings.height), 0.1)

    if branch.get("willow_relay_axis", False):
        return max(height * 0.24, _branch_length(parent) * 0.82)

    # The basal trunk is deliberately terminated early by relay architecture,
    # so comparing its large lateral scaffolds to *truncated trunk length* would
    # incorrectly shrink valid 5-7 m limbs.  Use tree height for level-0 parent.
    if parent_level <= 0:
        if level <= 1:
            return height * 0.56
        return height * 0.38

    if branch.get("willow_reparented_root", False) or "willow_relay_attachment_factor" in branch:
        return _branch_length(parent) * 0.68
    if level <= 2:
        return _branch_length(parent) * 0.72
    if level == 3:
        return _branch_length(parent) * 0.62
    return _branch_length(parent) * 0.54


def _scale_subtree_geometry(root, children, origin, scale):
    scale = float(scale)
    if scale >= 0.9995:
        return 0
    count = 0
    for branch in _subtree(root, children):
        new_points = []
        for point, radius in branch.get("points", ()):
            new_points.append((origin + (point - origin) * scale, float(radius)))
        if new_points:
            branch["points"] = new_points
            branch["length"] = generator._polyline_length(branch)
            count += 1
    return count


def _scale_subtree_radii(root, children, scale):
    scale = float(scale)
    if scale >= 0.9995:
        return 0
    count = 0
    for branch in _subtree(root, children):
        points = branch.get("points", ())
        if not points:
            continue
        branch["points"] = [(point.copy(), max(1.0e-6, float(radius) * scale)) for point, radius in points]
        count += 1
    return count


def _transform_subtree(root, children, old_origin, new_origin, rotation):
    count = 0
    for branch in _subtree(root, children):
        transformed = []
        for point, radius in branch.get("points", ()):
            transformed.append((new_origin + rotation @ (point - old_origin), float(radius)))
        if transformed:
            branch["points"] = transformed
            branch["length"] = generator._polyline_length(branch)
            count += 1
    return count


def _redistribute_reparented_roots(branches, children):
    """Softly spread transferred crown roots over each relay's useful span."""
    moved = 0
    by_parent = {}
    by_id = {int(branch.get("id", -1)): branch for branch in branches}

    for branch in branches:
        if "willow_relay_attachment_factor" not in branch:
            continue
        parent = by_id.get(int(branch.get("parent_id", -1)))
        if parent is None or not parent.get("willow_relay_axis", False):
            continue
        old_factor, _point, _radius, _tangent = _closest_frame(parent, branch["points"][0][0])
        by_parent.setdefault(int(parent.get("id", -1)), []).append((old_factor, branch))

    for parent_id, items in by_parent.items():
        if len(items) <= 1:
            continue
        parent = by_id[parent_id]
        items.sort(key=lambda entry: entry[0])
        count = len(items)
        min_factor = 0.30
        max_factor = 0.86

        # Spread over a broad span but preserve about half of the original
        # ordering/placement, avoiding a new artificial evenly-spaced whorl.
        targets = []
        for index, (old_factor, branch) in enumerate(items):
            ideal = min_factor + (max_factor - min_factor) * ((index + 0.5) / count)
            target = old_factor * 0.54 + ideal * 0.46
            targets.append(_clamp(target, 0.26, 0.90))

        # Enforce only a modest minimum separation.  Forward/backward passes
        # retain asymmetry while preventing several large roots from sharing one
        # tiny relay segment.
        minimum_gap = min(0.105, 0.46 / max(count, 1))
        for index in range(1, count):
            targets[index] = max(targets[index], targets[index - 1] + minimum_gap)
        overflow = max(0.0, targets[-1] - 0.90)
        if overflow > 0.0:
            targets = [value - overflow for value in targets]

        for (old_factor, branch), target_factor in zip(items, targets):
            if abs(target_factor - old_factor) < 0.018:
                branch["willow_relay_attachment_factor"] = float(target_factor)
                continue
            old_origin, _old_radius, old_tangent = _point_frame(parent, old_factor)
            new_origin, _new_radius, new_tangent = _point_frame(parent, target_factor)
            try:
                rotation = old_tangent.rotation_difference(new_tangent)
            except Exception:
                continue
            moved += _transform_subtree(branch, children, old_origin, new_origin, rotation)
            branch["willow_relay_attachment_factor"] = float(target_factor)
            branch["willow_hierarchy_redistributed"] = True

    return moved


def _normalize_reparented_scale(branches, children, settings):
    """Scale only roots transferred from the old trunk onto a thinner relay."""
    by_id = {int(branch.get("id", -1)): branch for branch in branches}
    scaled = 0

    for branch in branches:
        if "willow_relay_attachment_factor" not in branch:
            continue
        parent = by_id.get(int(branch.get("parent_id", -1)))
        points = branch.get("points", ())
        if parent is None or not points:
            continue

        _factor, attach, parent_radius, _tangent = _closest_frame(parent, points[0][0])
        child_radius = _root_core_radius(branch, settings)
        radius_limit = parent_radius * _radius_ratio_limit(branch, parent)
        radius_scale = min(1.0, radius_limit / max(child_radius, 1.0e-6))

        current_length = max(_branch_length(branch), 1.0e-6)
        length_limit = max(_length_limit(branch, parent, settings), float(settings.base_radius) * 0.30)
        geometry_scale = min(1.0, length_limit / current_length)

        # A subtree that becomes substantially shorter should also become
        # somewhat slimmer even if its old diameter happened to fit the limit.
        radius_scale = min(radius_scale, geometry_scale ** 0.72)

        if geometry_scale < 0.9995:
            scaled += _scale_subtree_geometry(branch, children, attach, geometry_scale)
        if radius_scale < 0.9995:
            scaled += _scale_subtree_radii(branch, children, radius_scale)

        if geometry_scale < 0.9995 or radius_scale < 0.9995:
            branch["willow_hierarchy_rescaled"] = True
            branch["willow_hierarchy_geometry_scale"] = float(geometry_scale)
            branch["willow_hierarchy_radius_scale"] = float(radius_scale)

    return scaled


def _individual_radius_caps(branches, children, settings):
    by_id = {int(branch.get("id", -1)): branch for branch in branches}
    corrected = 0

    # Parent-first order makes each subsequent comparison use the already-safe
    # parent diameter.
    ordered = sorted(branches, key=lambda branch: (int(branch.get("level", 0)), int(branch.get("id", 0))))
    for branch in ordered:
        if int(branch.get("level", 0)) <= 0 or branch.get("willow_root_buttress", False):
            continue
        parent = by_id.get(int(branch.get("parent_id", -1)))
        points = branch.get("points", ())
        if parent is None or not points:
            continue

        _factor, _attach, parent_radius, _tangent = _closest_frame(parent, points[0][0])
        child_radius = _root_core_radius(branch, settings)
        maximum = max(parent_radius * _radius_ratio_limit(branch, parent), float(settings.base_radius) * 0.004)
        if child_radius <= maximum * 1.002:
            continue

        scale = maximum / max(child_radius, 1.0e-6)
        corrected += _scale_subtree_radii(branch, children, scale)
        branch["willow_hierarchy_radius_capped"] = True
        branch["willow_hierarchy_radius_cap_scale"] = float(scale)

    return corrected


def _sibling_area_budget(branches, children, settings):
    """Leonardo-like local area budget for children sharing a parent segment."""
    by_id = {int(branch.get("id", -1)): branch for branch in branches}
    adjusted = 0

    for parent_id, siblings in children.items():
        parent = by_id.get(parent_id)
        if parent is None or len(siblings) < 2:
            continue

        entries = []
        for child in siblings:
            if child.get("willow_root_buttress", False) or not child.get("points"):
                continue
            factor, _attach, parent_radius, _tangent = _closest_frame(parent, child["points"][0][0])
            entries.append((factor, parent_radius, child))
        entries.sort(key=lambda item: item[0])

        # Build local attachment clusters.  Children far apart along the parent
        # do not compete for the same cross-section.
        groups = []
        current = []
        for entry in entries:
            if current and entry[0] - current[-1][0] > 0.095:
                groups.append(current)
                current = []
            current.append(entry)
        if current:
            groups.append(current)

        for group in groups:
            if len(group) < 2:
                continue
            parent_radius = max(item[1] for item in group)
            if parent_radius <= 1.0e-6:
                continue

            continuation = [item for item in group if item[2].get("willow_relay_axis", False)]
            laterals = [item for item in group if not item[2].get("willow_relay_axis", False)]
            if not laterals:
                continue

            # Approximate Leonardo's area relation (p=2): child cross-sectional
            # area should not collectively exceed the carrying parent section.
            # A relay continuation reserves part of that budget.
            reserved = 0.0
            for _factor, _pr, child in continuation:
                ratio = _root_core_radius(child, settings) / parent_radius
                reserved += ratio * ratio
            available = max(0.10, 0.82 - reserved)

            loads = []
            total = 0.0
            for _factor, _pr, child in laterals:
                ratio = _root_core_radius(child, settings) / parent_radius
                load = ratio * ratio
                loads.append((child, load))
                total += load
            if total <= available * 1.002:
                continue

            common_scale = math.sqrt(available / max(total, 1.0e-9))
            common_scale = _clamp(common_scale, 0.58, 1.0)
            for child, _load in loads:
                adjusted += _scale_subtree_radii(child, children, common_scale)
                child["willow_hierarchy_sibling_budget"] = True
                child["willow_hierarchy_sibling_scale"] = float(common_scale)

    return adjusted


def _normalize_lateral_lengths(branches, children, settings):
    """Catch grossly oversized laterals without shrinking valid basal scaffolds."""
    by_id = {int(branch.get("id", -1)): branch for branch in branches}
    adjusted = 0

    ordered = sorted(branches, key=lambda branch: (int(branch.get("level", 0)), int(branch.get("id", 0))))
    for branch in ordered:
        if int(branch.get("level", 0)) <= 0 or branch.get("willow_root_buttress", False):
            continue
        parent = by_id.get(int(branch.get("parent_id", -1)))
        if parent is None or not branch.get("points"):
            continue

        current = max(_branch_length(branch), 1.0e-6)
        maximum = _length_limit(branch, parent, settings)
        # Do not react to small natural variation; this is a guard against the
        # visibly impossible >parent-sized transfers seen in the screenshot.
        if current <= maximum * 1.08:
            continue

        scale = _clamp(maximum / current, 0.62, 1.0)
        origin = branch["points"][0][0].copy()
        adjusted += _scale_subtree_geometry(branch, children, origin, scale)
        adjusted += _scale_subtree_radii(branch, children, min(1.0, scale ** 0.72))
        branch["willow_hierarchy_length_capped"] = True
        branch["willow_hierarchy_length_scale"] = float(scale)

    return adjusted


def _generate_balanced(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    branches = list(branches)
    children = _children_map(branches)

    redistributed = _redistribute_reparented_roots(branches, children)
    # Rebuild attachment graph only for safety; IDs/parents did not change, but
    # this makes the intent explicit after subtree transforms.
    children = _children_map(branches)
    rescaled = _normalize_reparented_scale(branches, children, settings)
    length_fixed = _normalize_lateral_lengths(branches, children, settings)
    radius_fixed = _individual_radius_caps(branches, children, settings)
    sibling_fixed = _sibling_area_budget(branches, children, settings)

    try:
        trunk = min(branches, key=lambda branch: (int(branch.get("level", 0)), int(branch.get("id", 0))))
        trunk["willow_hierarchy_balance_version"] = 1
        trunk["willow_hierarchy_redistributed_nodes"] = int(redistributed)
        trunk["willow_hierarchy_rescaled_nodes"] = int(rescaled)
        trunk["willow_hierarchy_length_fixed_nodes"] = int(length_fixed)
        trunk["willow_hierarchy_radius_fixed_nodes"] = int(radius_fixed)
        trunk["willow_hierarchy_sibling_fixed_nodes"] = int(sibling_fixed)
    except Exception:
        pass

    # terminals contains references to the same dictionaries, so no ID/terminal
    # recomputation is required.  Their geometry has simply been corrected.
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_balanced
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
