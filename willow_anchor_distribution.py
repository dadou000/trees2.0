"""Post-deformation virtual foliage anchors for weeping willow.

The willow architecture stage creates real woody topology first, and the
structural-motion stage bends that hierarchy.  This module intentionally runs
after both of them so inner/outer canopy exposure is measured from the *final*
curved skeleton rather than from the pre-deformation branch layout.

Only non-terminal living branches become virtual foliage supports.  The scoring
strongly suppresses the central core, favors the outer half of the canopy, and
uses actual generated crown radius rather than the preset branch-length value.
"""

import math

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _smoothstep(lo, hi, value):
    if hi <= lo:
        return 1.0 if value >= hi else 0.0
    t = _clamp((value - lo) / (hi - lo))
    return t * t * (3.0 - 2.0 * t)


def _stable_unit(seed, value):
    x = (int(value) ^ int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def _radial(point):
    return math.hypot(float(point.x), float(point.y))


def _branch_exposure_sample(branch):
    """Use several outer-half samples so a curled-back tip is not misclassified."""
    values = []
    for factor in (0.52, 0.70, 0.86, 1.0):
        if factor >= 0.999:
            point = branch["points"][-1][0]
        else:
            point, _radius, _tangent = generator._point_on_polyline(branch, factor)
        values.append(_radial(point))
    return max(values) if values else 0.0


def _crown_radius_reference(branches, settings):
    samples = []
    for branch in branches:
        if branch.get("dead", False) or branch.get("willow_root_buttress", False):
            continue
        if int(branch.get("level", 0)) < 1 or len(branch.get("points", ())) < 2:
            continue
        samples.append(_branch_exposure_sample(branch))
    if not samples:
        return max(float(settings.branch_length), float(settings.base_radius) * 4.0, 1.0e-4)
    samples.sort()
    # A high percentile is more robust than the absolute maximum if one branch
    # happens to grow unusually far from the rest of the crown.
    index = min(len(samples) - 1, max(0, int(round((len(samples) - 1) * 0.90))))
    return max(samples[index], float(settings.base_radius) * 4.0, 1.0e-4)


def _anchor_metadata(branch, exposure):
    level = int(branch.get("level", 0))
    added = bool(branch.get("willow_architecture_added", False))
    if added:
        if level <= 1:
            weight, length_scale, max_bundles = 0.34, 0.50, 2
        elif level == 2:
            weight, length_scale, max_bundles = 0.68, 0.66, 3
        else:
            weight, length_scale, max_bundles = 0.54, 0.75, 2
    else:
        if level <= 1:
            weight, length_scale, max_bundles = 0.24, 0.46, 2
        elif level == 2:
            weight, length_scale, max_bundles = 0.48, 0.62, 3
        else:
            weight, length_scale, max_bundles = 0.40, 0.72, 2

    # Inner virtual supports are intentionally weak; outer supports carry more
    # of the short crown-fill sprays that connect into the long fringe.
    exposure_gain = 0.52 + 0.68 * _smoothstep(0.25, 0.88, exposure)
    length_gain = 0.80 + 0.24 * _smoothstep(0.38, 0.90, exposure)
    return weight * exposure_gain, length_scale * length_gain, max_bundles


def _add_virtual_anchors(settings, branches, terminals):
    existing_ids = {int(branch.get("id", -1)) for branch in terminals}
    extras = []
    height = max(float(settings.height), 1.0e-5)
    crown_radius = _crown_radius_reference(branches, settings)

    for branch in branches:
        branch_id = int(branch.get("id", -1))
        level = int(branch.get("level", 0))
        if (
            branch_id in existing_ids
            or level < 1
            or level > 3
            or branch.get("dead", False)
            or branch.get("willow_no_foliage", False)
            or len(branch.get("points", ())) < 2
        ):
            continue

        p_mid, _radius, _tangent = generator._point_on_polyline(branch, 0.66)
        p_end = branch["points"][-1][0]
        h = max(float(p_mid.z), float(p_end.z)) / height
        if h < 0.27:
            continue

        exposure = _clamp(_branch_exposure_sample(branch) / crown_radius)

        # The target has a dark but relatively open central core.  Level-1
        # supports especially should almost never grow curtains near the trunk.
        if level == 1 and exposure < 0.25:
            continue
        if level >= 2 and exposure < 0.16:
            continue

        base_probability = {1: 0.66, 2: 0.70, 3: 0.44}[level]
        if branch.get("willow_architecture_added", False):
            base_probability += 0.08

        radial_weight = 0.18 + 0.92 * _smoothstep(0.18, 0.82, exposure)
        upper_mid_weight = 0.58 + 0.48 * _smoothstep(0.30, 0.67, h)
        top_softening = 1.0 - 0.18 * _smoothstep(0.87, 1.02, h)
        probability = base_probability * radial_weight * upper_mid_weight * top_softening

        if _stable_unit(int(settings.seed) ^ 0x51A10A, branch_id * 53 + level * 17) > min(0.96, probability):
            continue

        weight, length_scale, max_bundles = _anchor_metadata(branch, exposure)
        branch["willow_aux_anchor"] = True
        branch["willow_anchor_weight"] = float(weight)
        branch["willow_length_scale"] = float(length_scale)
        branch["willow_fill_only"] = True
        branch["willow_max_bundles"] = int(max_bundles)
        branch["willow_anchor_level"] = int(level)
        branch["willow_radial_exposure"] = float(exposure)
        extras.append(branch)
        existing_ids.add(branch_id)

    terminals.extend(extras)
    try:
        trunk = branches[0]
        trunk["willow_anchor_distribution_version"] = 1
        trunk["willow_final_crown_radius"] = float(crown_radius)
        trunk["willow_virtual_anchor_count"] = len(extras)
        trunk["willow_real_terminal_count"] = len(terminals) - len(extras)
    except Exception:
        pass
    return extras


def _generate_with_final_anchors(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals
    terminals = list(terminals)
    _add_virtual_anchors(settings, branches, terminals)
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_final_anchors
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
