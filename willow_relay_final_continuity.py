"""Final continuous trunk-to-relay graft for weeping willow.

The early relay hand-off is topologically correct, but later junction flares and
Exact Boolean can expose the old parent termination as a horizontal shoulder or
notch.  The failure is caused by asking Boolean union to merge a capped parent
solid with a nearly touching continuation solid.

This WILLOW-only wrapper intentionally runs *after* ``organic_junctions`` and
before mesh construction.  It rewrites only the final trunk tail and the hidden
relay root overlap:

* the last trunk section is rebuilt as a smooth cubic transition toward the
  first relay direction;
* the old residual parent stub is discarded completely;
* local parent flare is normalized so the trunk cannot mushroom at takeover;
* the relay receives a continuation-class root diameter and starts slightly
  inside the trunk, giving Exact Boolean a robust overlapping solid;
* all visible relay points after its original root remain in place, preserving
  child attachments and the final crown shape.
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


def _safe_normalized(value, fallback):
    if value.length_squared <= 1.0e-12:
        return fallback.copy()
    return value.normalized()


def _lengths(branch):
    points = branch.get("points", ())
    cumulative = [0.0]
    total = 0.0
    for index in range(len(points) - 1):
        total += (points[index + 1][0] - points[index][0]).length
        cumulative.append(total)
    return cumulative, total


def _sample_length(branch, distance):
    points = branch.get("points", ())
    if not points:
        return Vector((0.0, 0.0, 0.0)), 0.0, Vector((0.0, 0.0, 1.0))
    if len(points) == 1:
        return points[0][0].copy(), float(points[0][1]), Vector((0.0, 0.0, 1.0))

    cumulative, total = _lengths(branch)
    target = _clamp(float(distance), 0.0, total)
    for index in range(len(points) - 1):
        if cumulative[index + 1] + 1.0e-9 < target:
            continue
        a, ar = points[index]
        b, br = points[index + 1]
        delta = b - a
        segment = max(delta.length, 1.0e-9)
        local = _clamp((target - cumulative[index]) / segment)
        tangent = _safe_normalized(delta, Vector((0.0, 0.0, 1.0)))
        return a.lerp(b, local), float(ar) + (float(br) - float(ar)) * local, tangent
    tangent = _safe_normalized(points[-1][0] - points[-2][0], Vector((0.0, 0.0, 1.0)))
    return points[-1][0].copy(), float(points[-1][1]), tangent


def _closest_frame(branch, target):
    points = branch.get("points", ())
    if len(points) < 2:
        radius = float(points[0][1]) if points else 0.0
        point = points[0][0].copy() if points else target.copy()
        return 0.0, point, radius, Vector((0.0, 0.0, 1.0))

    cumulative, total = _lengths(branch)
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
            segment = math.sqrt(length_sq)
            best_distance = distance
            best_length = cumulative[index] + segment * local
            best_point = projected
            best_radius = float(ar) + (float(br) - float(ar)) * local
            best_tangent = delta / segment
    return best_length, best_point, best_radius, best_tangent


def _bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    return (
        p0 * (u ** 3)
        + p1 * (3.0 * u * u * t)
        + p2 * (3.0 * u * t * t)
        + p3 * (t ** 3)
    )


def _first_relay(branches, trunk):
    candidates = [
        branch for branch in branches
        if branch.get("willow_relay_axis", False)
        and int(branch.get("parent_id", -1)) == int(trunk.get("id", -1))
        and len(branch.get("points", ())) >= 2
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda branch: int(branch.get("willow_relay_order", 1)))


def _rewrite_trunk_tail(trunk, relay, settings):
    relay_points = relay.get("points", ())
    if len(relay_points) < 2 or len(trunk.get("points", ())) < 2:
        return False

    original_relay_root = relay_points[0][0].copy()
    attach_length, attach, attach_radius, parent_tangent = _closest_frame(trunk, original_relay_root)
    _cumulative, trunk_total = _lengths(trunk)
    if trunk_total <= 1.0e-6:
        return False

    relay_tangent = _safe_normalized(
        relay_points[min(2, len(relay_points) - 1)][0] - relay_points[0][0],
        _safe_normalized(relay_points[1][0] - relay_points[0][0], parent_tangent),
    )

    # Use a physically meaningful blend length.  This overwrites the local flare
    # zone created by generic junction preprocessing and prevents a mushroom cap.
    blend_length = _clamp(
        max(float(settings.base_radius) * 0.70, attach_radius * 1.80),
        0.42,
        min(1.15, max(0.42, attach_length * 0.42)),
    )
    blend_start_length = max(0.0, attach_length - blend_length)
    blend_start, blend_radius, blend_tangent = _sample_length(trunk, blend_start_length)

    # Normalize any accumulated parent flare.  A continuation must taper through
    # the takeover, not grow wider just before it.
    support_radius = min(float(attach_radius), float(blend_radius) * 1.015)
    support_radius = max(support_radius, float(settings.base_radius) * 0.045)
    relay_root_radius = support_radius * 0.885

    overlap = _clamp(support_radius * 0.24, 0.045, 0.12)
    trunk_end = attach + relay_tangent * (overlap * 0.52)

    # Keep all trunk samples safely below the blend region, then replace its tail
    # with a 5-sample cubic that arrives already tangent to the relay.
    cumulative, _total = _lengths(trunk)
    prefix = []
    for index, pair in enumerate(trunk.get("points", ())):
        if cumulative[index] < blend_start_length - 1.0e-6:
            prefix.append((pair[0].copy(), float(pair[1])))
        else:
            break

    p0 = blend_start
    p3 = trunk_end
    chord = max((p3 - p0).length, 1.0e-4)
    p1 = p0 + _safe_normalized(blend_tangent, parent_tangent) * chord * 0.34
    p2 = p3 - relay_tangent * chord * 0.30

    rebuilt = list(prefix)
    for index in range(5):
        t = index / 4.0
        eased = _smoothstep(t)
        position = _bezier(p0, p1, p2, p3, t)
        radius = float(blend_radius) * (1.0 - eased) + (relay_root_radius * 1.025) * eased
        if rebuilt and (position - rebuilt[-1][0]).length <= 1.0e-6:
            rebuilt[-1] = (position, radius)
        else:
            rebuilt.append((position, radius))

    trunk["points"] = rebuilt
    trunk["length"] = generator._polyline_length(trunk)
    trunk["willow_relay_final_continuity"] = True
    trunk["willow_relay_final_blend_length"] = float(blend_length)
    trunk["willow_relay_final_overlap"] = float(overlap)

    # Start the relay inside the parent volume.  Keep every original visible
    # downstream position unchanged so existing child attachment coordinates stay
    # exactly where the final crown passes placed them.
    hidden_root = attach - parent_tangent * overlap
    original = list(relay_points)
    original[0] = (attach.copy(), relay_root_radius)

    # Smooth only radii through the first few existing samples; positions are
    # untouched.  This removes an immediate diameter cliff without detaching any
    # descendants that happen to originate on the early relay.
    count = min(4, len(original))
    downstream_radius = float(original[count - 1][1])
    for index in range(count):
        t = index / max(count - 1, 1)
        eased = _smoothstep(t)
        target_radius = relay_root_radius * (1.0 - eased) + downstream_radius * eased
        original[index] = (original[index][0].copy(), max(target_radius, downstream_radius * 0.94))

    relay["points"] = [(hidden_root, relay_root_radius * 1.015)] + original
    relay["length"] = generator._polyline_length(relay)
    relay["willow_relay_boolean_overlap"] = True
    relay["willow_relay_continuation_radius"] = float(relay_root_radius)
    return True


def _generate_continuity(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    trunk = min(branches, key=lambda branch: (int(branch.get("level", 0)), int(branch.get("id", 0))))
    relay = _first_relay(branches, trunk)
    if relay is None:
        return branches, terminals

    if _rewrite_trunk_tail(trunk, relay, settings):
        trunk["willow_relay_final_continuity_version"] = 1
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_continuity
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
