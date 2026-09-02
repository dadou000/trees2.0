"""Clean sympodial hand-off between the basal trunk and first willow relay.

The relay architecture deliberately terminates the original trunk shortly after
the first takeover shoot.  Earlier versions left roughly 5-7% of the full trunk
length above that attachment.  On a 12-13 m willow this becomes a visibly huge
50-80 cm bare stump, while the actual relay still reads like a lateral branch.

This wrapper runs immediately after ``willow_relay_architecture`` and converts
that construction into a true visual continuation:

* the obsolete parent axis extends only a short physical distance beyond the
  relay attachment and tapers aggressively into a subordinate nub;
* any direct trunk children that occupied the discarded residual section are
  moved, with their complete subtrees, onto the early first relay;
* the first relay inherits most of the parent diameter and parent tangent over
  a short C1-like cubic transition;
* branch IDs remain unchanged and all transforms are deterministic.

The later structural-motion, sinuous, hierarchy-balance and organic-junction
passes still operate normally on this corrected graph.
"""

import math

from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _smoothstep(value):
    t = _clamp(value)
    return t * t * (3.0 - 2.0 * t)


def _safe_normalized(vector, fallback):
    if vector.length_squared <= 1.0e-12:
        return fallback.copy()
    return vector.normalized()


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
            seg = math.sqrt(length_sq)
            best_distance = distance
            best_length = cumulative[index] + seg * local
            best_point = projected
            best_radius = float(ar) + (float(br) - float(ar)) * local
            best_tangent = delta / seg
    return _clamp(best_length / total), best_point, best_radius, best_tangent


def _sample_at_length(branch, distance):
    points = branch.get("points", ())
    if not points:
        return Vector((0.0, 0.0, 0.0)), 0.0, Vector((0.0, 0.0, 1.0))
    if len(points) == 1:
        return points[0][0].copy(), float(points[0][1]), Vector((0.0, 0.0, 1.0))

    cumulative, total = _cumulative(branch)
    target = _clamp(distance, 0.0, total)
    for index in range(len(points) - 1):
        if cumulative[index + 1] + 1.0e-9 < target:
            continue
        a, ar = points[index]
        b, br = points[index + 1]
        delta = b - a
        seg = max(delta.length, 1.0e-9)
        local = _clamp((target - cumulative[index]) / seg)
        tangent = _safe_normalized(delta, Vector((0.0, 0.0, 1.0)))
        return a.lerp(b, local), float(ar) + (float(br) - float(ar)) * local, tangent
    delta = points[-1][0] - points[-2][0]
    return points[-1][0].copy(), float(points[-1][1]), _safe_normalized(delta, Vector((0.0, 0.0, 1.0)))


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


def _transform_subtree(root, children, old_origin, new_origin, rotation, level_delta=0):
    moved = 0
    for branch in _subtree(root, children):
        transformed = []
        for point, radius in branch.get("points", ()):
            transformed.append((new_origin + rotation @ (point - old_origin), float(radius)))
        if transformed:
            branch["points"] = transformed
            branch["length"] = generator._polyline_length(branch)
            moved += 1
        if level_delta:
            branch["level"] = min(4, max(1, int(branch.get("level", 1)) + level_delta))
    return moved


def _trim_parent_stub(trunk, attach_length, attach_radius, settings):
    cumulative, total = _cumulative(trunk)
    if total <= 1.0e-8:
        return 0.0

    # Physical, not normalized, stub length.  This keeps the visual result stable
    # when tree height changes and prevents a percentage of a 13 m trunk becoming
    # a massive bare limb.
    stub_length = _clamp(float(settings.base_radius) * 0.22, 0.10, 0.20)
    cutoff_length = min(total, attach_length + stub_length)
    attach_point, _ar, attach_tangent = _sample_at_length(trunk, attach_length)
    tip_point, _tip_r, _tip_tangent = _sample_at_length(trunk, cutoff_length)

    output = []
    for index, (point, radius) in enumerate(trunk.get("points", ())):
        if cumulative[index] < attach_length - 1.0e-6:
            output.append((point.copy(), float(radius)))
        else:
            break

    # Insert an exact attachment ring, then only one/two subordinate tail rings.
    output.append((attach_point.copy(), float(attach_radius)))
    if stub_length > 0.13:
        mid_distance = attach_length + stub_length * 0.52
        mid_point, _mr, _mt = _sample_at_length(trunk, mid_distance)
        mid_radius = max(float(settings.base_radius) * 0.028, attach_radius * 0.42)
        output.append((mid_point, mid_radius))

    tip_radius = max(float(settings.base_radius) * 0.012, attach_radius * 0.075)
    # If the old polyline has almost no usable tail, continue along the parent
    # tangent so the nub does not collapse into a zero-area Boolean cap.
    if (tip_point - attach_point).length < stub_length * 0.55:
        tip_point = attach_point + attach_tangent * stub_length
    output.append((tip_point, tip_radius))

    trunk["points"] = output
    trunk["length"] = generator._polyline_length(trunk)
    trunk["willow_relay_parent_stub"] = True
    trunk["willow_relay_stub_length"] = float(stub_length)
    return cutoff_length


def _bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    return p0 * (u ** 3) + p1 * (3.0 * u * u * t) + p2 * (3.0 * u * t * t) + p3 * (t ** 3)


def _blend_relay_root(relay, attach_point, attach_radius, parent_tangent):
    points = relay.get("points", ())
    if len(points) < 4:
        return False

    cumulative, total = _cumulative(relay)
    if total <= 1.0e-6:
        return False

    blend_length = min(total * 0.20, max(attach_radius * 2.2, total * 0.11))
    end_index = 2
    while end_index < len(points) - 1 and cumulative[end_index] < blend_length:
        end_index += 1
    end_index = min(max(2, end_index), len(points) - 1)

    p0 = attach_point.copy()
    p3 = points[end_index][0].copy()
    chord = p3 - p0
    if chord.length <= 1.0e-5:
        return False

    downstream_index = min(len(points) - 1, end_index + 1)
    downstream = _safe_normalized(
        points[downstream_index][0] - points[max(0, end_index - 1)][0],
        _safe_normalized(chord, parent_tangent),
    )
    start_direction = _safe_normalized(
        parent_tangent * 0.72 + _safe_normalized(points[1][0] - points[0][0], parent_tangent) * 0.28,
        parent_tangent,
    )
    p1 = p0 + start_direction * (chord.length * 0.38)
    p2 = p3 - downstream * (chord.length * 0.30)

    desired_root_radius = attach_radius * 0.88
    end_radius = float(points[end_index][1])
    new_points = list(points)
    for index in range(end_index + 1):
        t = cumulative[index] / max(cumulative[end_index], 1.0e-6)
        eased = _smoothstep(t)
        position = p0 if index == 0 else (p3 if index == end_index else _bezier(p0, p1, p2, p3, t))
        radius = desired_root_radius * (1.0 - eased) + end_radius * eased
        new_points[index] = (position, max(radius, end_radius * 0.94))

    relay["points"] = new_points
    relay["length"] = generator._polyline_length(relay)
    relay["willow_relay_handoff_blended"] = True
    relay["willow_relay_handoff_radius_ratio"] = 0.88
    return True


def _move_residual_children(branches, trunk, relay, cutoff_length, children):
    trunk_id = int(trunk.get("id", -1))
    relay_id = int(relay.get("id", -1))
    current_total = max(_cumulative(trunk)[1], 1.0e-6)
    moved = 0

    candidates = []
    for child in children.get(trunk_id, ()):
        if int(child.get("id", -1)) == relay_id or child.get("willow_root_buttress", False):
            continue
        if not child.get("points"):
            continue
        factor, old_origin, _radius, old_tangent = _closest_frame(trunk, child["points"][0][0])
        distance = factor * current_total
        if distance > cutoff_length - 1.0e-5:
            candidates.append((distance, child, old_origin, old_tangent))

    candidates.sort(key=lambda item: item[0])
    count = len(candidates)
    for index, (_distance, child, old_origin, old_tangent) in enumerate(candidates):
        # Early relay placement: enough separation to keep the hand-off readable,
        # but never into the heavily blended first 10% of the continuation.
        target_factor = 0.16 + (0.12 * ((index + 0.5) / max(count, 1)))
        new_origin, _new_radius, new_tangent = generator._point_on_polyline(relay, target_factor)
        try:
            rotation = old_tangent.rotation_difference(new_tangent)
        except Exception:
            continue
        moved += _transform_subtree(child, children, old_origin, new_origin, rotation, level_delta=1)
        child["parent_id"] = relay_id
        child["willow_relay_attachment_factor"] = float(target_factor)
        child["willow_relay_handoff_reparented"] = True
    return moved


def _generate_handoff(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    trunk = min(branches, key=lambda branch: (int(branch.get("level", 0)), int(branch.get("id", 0))))
    relay_candidates = [
        branch for branch in branches
        if branch.get("willow_relay_axis", False)
        and int(branch.get("parent_id", -1)) == int(trunk.get("id", -1))
    ]
    if not relay_candidates:
        return branches, terminals

    first_relay = min(relay_candidates, key=lambda branch: int(branch.get("willow_relay_order", 1)))
    if not first_relay.get("points") or len(trunk.get("points", ())) < 2:
        return branches, terminals

    attach_factor, attach_point, attach_radius, parent_tangent = _closest_frame(trunk, first_relay["points"][0][0])
    _cum, trunk_total = _cumulative(trunk)
    attach_length = attach_factor * trunk_total

    # Move any direct child that would otherwise be chopped off before trimming.
    children = _children_map(branches)
    desired_stub = _clamp(float(settings.base_radius) * 0.22, 0.10, 0.20)
    desired_cutoff = min(trunk_total, attach_length + desired_stub)
    moved = _move_residual_children(branches, trunk, first_relay, desired_cutoff, children)

    _trim_parent_stub(trunk, attach_length, attach_radius, settings)
    _blend_relay_root(first_relay, attach_point, attach_radius, parent_tangent)

    trunk["willow_relay_handoff_version"] = 1
    trunk["willow_relay_handoff_moved_nodes"] = int(moved)
    trunk["willow_trunk_cutoff_fraction"] = float(
        min(1.0, (attach_length + desired_stub) / max(trunk_total, 1.0e-6))
    )
    trunk["willow_trunk_terminated"] = True
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_handoff
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
