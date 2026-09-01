"""Continuous crown-envelope equalization for mature weeping willow.

The 0.9.2 outward-distribution pass removes the worst proximal recursive clutter,
but hard structural pruning and discrete terminal classes can leave a scalloped,
rough crown.  This stage runs on the *final curved/spread skeleton* after virtual
anchor scoring and before the terminal-budget bridge.

It does not move the woody skeleton.  Instead it treats the final crown as a
continuous angular support field:

* terminal/virtual-support occupancy is accumulated in azimuth sectors;
* the field is circularly blurred so neighbouring sectors influence each other;
* overloaded sectors are gently attenuated and sparse sectors are boosted;
* real terminal weight/length is computed continuously from exposure and height,
  replacing abrupt inner/middle/outer visual transitions;
* genuinely empty sectors may receive one short fill-only virtual support chosen
  from an existing non-terminal branch, rather than creating new woody geometry.

The result should preserve the cleaner 0.9.2 core while producing a smoother,
more continuous broad willow crown instead of a lumpy/scalloped outline.
"""

import math

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


_SECTOR_COUNT = {
    "LOD0": 24,
    "LOD1": 20,
    "LOD2": 16,
    "LOD3": 12,
    "LOD4": 8,
}


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


def _origin(branches):
    for branch in branches:
        if int(branch.get("level", 0)) == 0 and branch.get("points"):
            return branch["points"][0][0].copy()
    for branch in branches:
        if branch.get("points"):
            return branch["points"][0][0].copy()
    return None


def _radial(point, origin):
    dx = float(point.x - origin.x)
    dy = float(point.y - origin.y)
    return math.hypot(dx, dy)


def _azimuth(point, origin):
    angle = math.atan2(float(point.y - origin.y), float(point.x - origin.x))
    if angle < 0.0:
        angle += math.tau
    return angle


def _sector(angle, count):
    return int(math.floor((angle / math.tau) * count)) % count


def _sample_outer_point(branch):
    """Representative point for crown placement, robust to a curled-back tip."""
    best = None
    best_radius = -1.0
    for factor in (0.58, 0.72, 0.86, 1.0):
        if factor >= 0.999:
            point = branch["points"][-1][0]
        else:
            point, _radius, _tangent = generator._point_on_polyline(branch, factor)
        # Use XY radius about world origin only for selecting the local outer
        # sample.  Absolute exposure is calculated later around the trunk origin.
        radius = math.hypot(float(point.x), float(point.y))
        if radius > best_radius:
            best_radius = radius
            best = point
    return best if best is not None else branch["points"][-1][0]


def _crown_radius(branches, origin, settings):
    values = []
    for branch in branches:
        if (
            branch.get("dead", False)
            or branch.get("willow_root_buttress", False)
            or int(branch.get("level", 0)) < 1
            or len(branch.get("points", ())) < 2
        ):
            continue
        values.append(_radial(_sample_outer_point(branch), origin))
    if not values:
        return max(float(settings.branch_length), float(settings.base_radius) * 4.0, 1.0)
    values.sort()
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * 0.90))))
    return max(values[index], float(settings.base_radius) * 4.0, 1.0e-4)


def _height_fraction(branch, settings):
    height = max(float(settings.height), 1.0e-5)
    point = _sample_outer_point(branch)
    return _clamp(float(point.z) / height)


def _dome_target_exposure(height_fraction):
    """Smooth rounded willow shell target as a function of height.

    The lower crown is narrower near the trunk, the mid/upper crown is broad,
    and the apex closes gently rather than forming spikes.
    """
    h = _clamp(height_fraction)
    lower = _smoothstep(0.20, 0.48, h)
    upper_close = 1.0 - 0.46 * _smoothstep(0.82, 1.02, h)
    shoulder = 0.68 + 0.22 * math.sin(math.pi * _clamp((h - 0.18) / 0.82))
    return _clamp((0.48 + 0.34 * lower) * upper_close + shoulder * 0.18, 0.42, 0.94)


def _support_weight(branch):
    if branch.get("willow_aux_anchor", False):
        return _clamp(float(branch.get("willow_anchor_weight", 0.45)), 0.18, 1.0)
    return _clamp(float(branch.get("willow_terminal_weight", 1.0)), 0.20, 1.15)


def _occupancy(terminals, origin, crown_radius, sector_count, settings):
    field = [0.0] * sector_count
    max_exposure = [0.0] * sector_count
    counts = [0] * sector_count

    for branch in terminals:
        if branch.get("dead", False) or len(branch.get("points", ())) < 2:
            continue
        point = _sample_outer_point(branch)
        sector = _sector(_azimuth(point, origin), sector_count)
        exposure = _clamp(_radial(point, origin) / max(crown_radius, 1.0e-5))
        h = _height_fraction(branch, settings)

        # Mid/upper crown supports contribute most to perceived silhouette.
        height_gain = 0.52 + 0.48 * _smoothstep(0.28, 0.68, h)
        field[sector] += _support_weight(branch) * height_gain
        max_exposure[sector] = max(max_exposure[sector], exposure)
        counts[sector] += 1

    return field, max_exposure, counts


def _circular_blur(values, passes=2):
    result = list(values)
    count = len(result)
    if count <= 2:
        return result
    for _pass in range(max(1, passes)):
        source = result
        result = []
        for index in range(count):
            value = (
                source[(index - 2) % count] * 0.08
                + source[(index - 1) % count] * 0.24
                + source[index] * 0.36
                + source[(index + 1) % count] * 0.24
                + source[(index + 2) % count] * 0.08
            )
            result.append(value)
    return result


def _robust_target(values):
    positive = sorted(value for value in values if value > 1.0e-6)
    if not positive:
        return 1.0
    lo = int(len(positive) * 0.20)
    hi = max(lo + 1, int(math.ceil(len(positive) * 0.80)))
    trimmed = positive[lo:hi]
    return max(sum(trimmed) / max(len(trimmed), 1), 0.20)


def _sector_gain(index, raw, smooth, target):
    local = max(smooth[index], 0.06)
    # Blend global target with neighbouring density.  This avoids forcing a
    # perfectly circular hedge while still reducing obvious holes/lumps.
    desired = target * 0.58 + local * 0.42
    ratio = desired / max(raw[index] * 0.55 + local * 0.45, 0.08)
    return _clamp(ratio, 0.72, 1.34)


def _continuous_terminal_budget(branch, origin, crown_radius, sector_gain, settings):
    point = _sample_outer_point(branch)
    exposure = _clamp(_radial(point, origin) / max(crown_radius, 1.0e-5))
    h = _height_fraction(branch, settings)
    target_exposure = _dome_target_exposure(h)

    shell_error = exposure - target_exposure
    shell_fit = 1.0 - _clamp(abs(shell_error) / 0.42)
    outerness = _smoothstep(0.28, 0.84, exposure)
    core_gate = _smoothstep(0.16, 0.44, exposure)

    # Continuous density/length response.  There are deliberately no discrete
    # inner/middle/outer thresholds here.
    weight = 0.30 + 0.58 * outerness + 0.16 * shell_fit
    weight *= 0.84 + 0.18 * sector_gain
    weight *= 0.82 + 0.18 * core_gate

    length_scale = 0.48 + 0.42 * outerness + 0.12 * shell_fit
    length_scale *= 0.90 + 0.12 * sector_gain

    # Apex supports should be shorter so the top closes smoothly instead of
    # producing isolated antenna curtains.
    apex = _smoothstep(0.82, 1.0, h)
    length_scale *= 1.0 - 0.18 * apex

    fill_only = exposure < 0.27
    if fill_only:
        weight = min(weight, 0.46)
        length_scale = min(length_scale, 0.58)

    branch["willow_terminal_exposure"] = float(exposure)
    branch["willow_terminal_target_exposure"] = float(target_exposure)
    branch["willow_terminal_sector_gain"] = float(sector_gain)
    branch["willow_terminal_weight"] = float(_clamp(weight, 0.26, 1.08))
    branch["willow_terminal_length_scale"] = float(_clamp(length_scale, 0.44, 1.06))
    branch["willow_terminal_fill_only"] = bool(fill_only)


def _adjust_virtual_anchor(branch, origin, crown_radius, sector_gain, settings):
    point = _sample_outer_point(branch)
    exposure = _clamp(_radial(point, origin) / max(crown_radius, 1.0e-5))
    h = _height_fraction(branch, settings)
    target_exposure = _dome_target_exposure(h)
    shell_fit = 1.0 - _clamp(abs(exposure - target_exposure) / 0.44)

    weight = float(branch.get("willow_anchor_weight", 0.45))
    length_scale = float(branch.get("willow_length_scale", 0.62))

    weight *= _clamp(0.80 + 0.22 * sector_gain + 0.10 * shell_fit, 0.74, 1.22)
    length_scale *= _clamp(0.88 + 0.12 * sector_gain + 0.08 * shell_fit, 0.82, 1.15)

    # Keep virtual supports as fill; their purpose is envelope continuity, not
    # another set of full floor-reaching outer curtains.
    branch["willow_anchor_weight"] = float(_clamp(weight, 0.20, 0.86))
    branch["willow_length_scale"] = float(_clamp(length_scale, 0.40, 0.86))
    branch["willow_fill_only"] = True
    branch["willow_radial_exposure"] = float(exposure)
    branch["willow_crown_sector_gain"] = float(sector_gain)


def _candidate_score(branch, origin, crown_radius, settings):
    if (
        branch.get("dead", False)
        or branch.get("willow_no_foliage", False)
        or branch.get("willow_root_buttress", False)
        or len(branch.get("points", ())) < 2
    ):
        return -1.0
    level = int(branch.get("level", 0))
    if level < 2 or level > 3:
        return -1.0

    point = _sample_outer_point(branch)
    exposure = _clamp(_radial(point, origin) / max(crown_radius, 1.0e-5))
    h = _height_fraction(branch, settings)
    if h < 0.30 or exposure < 0.20:
        return -1.0

    target = _dome_target_exposure(h)
    shell_fit = 1.0 - _clamp(abs(exposure - target) / 0.44)
    return shell_fit * 1.10 + exposure * 0.55 + _smoothstep(0.34, 0.72, h) * 0.25


def _fill_empty_sectors(settings, branches, terminals, origin, crown_radius, raw, smooth, target, sector_count):
    existing = {int(branch.get("id", -1)) for branch in terminals}
    candidates = [[] for _ in range(sector_count)]

    for branch in branches:
        branch_id = int(branch.get("id", -1))
        if branch_id in existing:
            continue
        score = _candidate_score(branch, origin, crown_radius, settings)
        if score < 0.0:
            continue
        point = _sample_outer_point(branch)
        index = _sector(_azimuth(point, origin), sector_count)
        jitter = _stable_unit(int(settings.seed) ^ 0xC8017, branch_id * 71 + index * 13) * 0.04
        candidates[index].append((score + jitter, branch))

    added = []
    for index in range(sector_count):
        # Only genuine gaps get synthetic support.  Merely light sectors are
        # handled continuously by density gain above.
        if smooth[index] >= target * 0.47 or raw[index] >= target * 0.32:
            continue
        if not candidates[index]:
            continue

        candidates[index].sort(key=lambda item: item[0], reverse=True)
        _score, branch = candidates[index][0]
        branch["willow_aux_anchor"] = True
        branch["willow_envelope_gap_fill"] = True
        branch["willow_anchor_weight"] = 0.42
        branch["willow_length_scale"] = 0.58
        branch["willow_fill_only"] = True
        branch["willow_max_bundles"] = 2
        branch["willow_anchor_level"] = int(branch.get("level", 0))
        branch["willow_radial_exposure"] = float(
            _clamp(_radial(_sample_outer_point(branch), origin) / max(crown_radius, 1.0e-5))
        )
        terminals.append(branch)
        existing.add(int(branch.get("id", -1)))
        added.append(branch)

    return added


def _generate_with_envelope(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    origin = _origin(branches)
    if origin is None:
        return branches, terminals

    sector_count = _SECTOR_COUNT.get(str(settings.lod), _SECTOR_COUNT["LOD0"])
    crown_radius = _crown_radius(branches, origin, settings)
    raw, max_exposure, counts = _occupancy(terminals, origin, crown_radius, sector_count, settings)
    smooth = _circular_blur(raw, passes=2)
    target = _robust_target(smooth)
    gains = [_sector_gain(index, raw, smooth, target) for index in range(sector_count)]

    # Apply continuous budgets to existing supports first.
    for branch in terminals:
        if branch.get("dead", False) or len(branch.get("points", ())) < 2:
            continue
        point = _sample_outer_point(branch)
        index = _sector(_azimuth(point, origin), sector_count)
        gain = gains[index]
        if branch.get("willow_aux_anchor", False):
            _adjust_virtual_anchor(branch, origin, crown_radius, gain, settings)
        else:
            _continuous_terminal_budget(branch, origin, crown_radius, gain, settings)

    added = _fill_empty_sectors(
        settings,
        branches,
        terminals,
        origin,
        crown_radius,
        raw,
        smooth,
        target,
        sector_count,
    )

    try:
        trunk = next(branch for branch in branches if int(branch.get("level", 0)) == 0)
        trunk["willow_crown_envelope_version"] = 1
        trunk["willow_crown_envelope_sectors"] = int(sector_count)
        trunk["willow_crown_envelope_target"] = float(target)
        trunk["willow_crown_envelope_gap_fill"] = int(len(added))
        trunk["willow_crown_envelope_min_gain"] = float(min(gains) if gains else 1.0)
        trunk["willow_crown_envelope_max_gain"] = float(max(gains) if gains else 1.0)
    except Exception:
        pass

    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_envelope
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
