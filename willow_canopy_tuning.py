"""Final radial/vertical canopy shaping for weeping willow.

This runs after willow_foliage_fix has generated continuous curtain cards.  It
works at *strand* granularity so it never punches random holes into a curtain:

* central-core strands are deterministically thinned,
* outer exposed strands are retained preferentially,
* upper antenna-like curtains are shortened,
* middle/outer curtains receive broader length variation,
* a small subset of exposed fringe strands may stretch slightly longer.

The underlying card overlap, leaf scale and LOD ordering remain authoritative.
"""

import math

from . import foliage_assembly, generator


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


def _crown_radius_reference(terminals, settings):
    samples = []
    for branch in terminals:
        if branch.get("dead", False) or branch.get("willow_root_buttress", False):
            continue
        points = branch.get("points", ())
        if len(points) < 2:
            continue
        values = []
        for factor in (0.55, 0.74, 0.90, 1.0):
            if factor >= 0.999:
                point = points[-1][0]
            else:
                point, _radius, _tangent = generator._point_on_polyline(branch, factor)
            values.append(_radial(point))
        if values:
            samples.append(max(values))
    if not samples:
        return max(float(settings.branch_length), float(settings.base_radius) * 4.0, 1.0e-4)
    samples.sort()
    index = min(len(samples) - 1, max(0, int(round((len(samples) - 1) * 0.90))))
    return max(samples[index], float(settings.base_radius) * 4.0, 1.0e-4)


def _strand_groups(records):
    groups = {}
    loose = []
    for record in records:
        strand_id = int(record.get("strand_id", -1))
        if int(record.get("assembly_role", -1)) != 2 or strand_id < 0:
            loose.append(record)
            continue
        groups.setdefault(strand_id, []).append(record)
    return groups, loose


def _keep_probability(height_fraction, exposure, virtual):
    h = _clamp(height_fraction)
    e = _clamp(exposure)

    # Strongly suppress the inner core. The target still has dark internal
    # foliage, but it is not a solid cylinder of floor-length curtains.
    radial = 0.14 + 0.94 * _smoothstep(0.18, 0.78, e)
    upper_mid = 0.78 + 0.22 * _smoothstep(0.34, 0.66, h)
    top_softening = 1.0 - 0.20 * _smoothstep(0.86, 1.01, h)
    lower_inner_softening = 1.0
    if h < 0.42:
        lower_inner_softening = 0.72 + 0.28 * _smoothstep(0.28, 0.58, e)
    if virtual:
        radial *= 0.90 + 0.10 * _smoothstep(0.45, 0.85, e)
    return _clamp(radial * upper_mid * top_softening * lower_inner_softening, 0.06, 1.0)


def _length_stretch(height_fraction, exposure, accent, virtual, jitter):
    h = _clamp(height_fraction)
    e = _clamp(exposure)

    # Radial exposure is now the main driver of fringe length. Inner curtains
    # are shorter; outer curtains can hang much farther and form the silhouette.
    radial_scale = 0.76 + 0.32 * _smoothstep(0.24, 0.88, e)

    if h >= 0.84:
        height_scale = 0.76 + 0.10 * _smoothstep(0.45, 0.90, e)
    elif h >= 0.58:
        height_scale = 0.94
    elif h >= 0.38:
        height_scale = 1.00
    else:
        height_scale = 0.92

    if virtual:
        height_scale *= 0.94

    variation = 0.88 + 0.24 * jitter
    stretch = radial_scale * height_scale * variation

    if accent and e >= 0.58 and h < 0.84:
        stretch *= 1.06 + 0.08 * _smoothstep(0.58, 0.96, e)

    # Continuous cards tolerate a modest stretch because the source generator
    # deliberately uses high overlap. Keep the cap conservative.
    return _clamp(stretch, 0.58, 1.15)


def _generate_tuned_canopy(settings, terminals, cfg, profile, assembly):
    records = _PREVIOUS_GENERATE(settings, terminals, cfg, profile, assembly)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not records:
        return records

    crown_radius = _crown_radius_reference(terminals, settings)
    groups, loose = _strand_groups(records)
    output = list(loose)

    for strand_id, cards in groups.items():
        ordered = sorted(cards, key=lambda record: float(record.get("strand_t", 0.0)))
        if not ordered:
            continue
        anchor = ordered[0]["position"].copy()
        h = _clamp(float(ordered[0].get("willow_anchor_height", anchor.z / max(float(settings.height), 1.0e-5))))
        exposure = _clamp(_radial(anchor) / crown_radius)
        virtual = bool(ordered[0].get("willow_virtual_anchor", False))
        accent = any(bool(record.get("willow_accent_strand", False)) for record in ordered)

        keep_p = _keep_probability(h, exposure, virtual)
        if _stable_unit(int(settings.seed) ^ 0xC4110F5, int(strand_id) * 101 + 17) > keep_p:
            continue

        jitter = _stable_unit(int(settings.seed) ^ 0x1EAF5EED, int(strand_id) * 211 + 29)
        stretch = _length_stretch(h, exposure, accent, virtual, jitter)

        # Rescale the whole card chain around its attachment card. This changes
        # curtain length without changing card size or punching coverage holes.
        for record in ordered:
            offset = record["position"] - anchor
            record["position"] = anchor + offset * stretch
            record["willow_radial_exposure"] = float(exposure)
            record["willow_length_stretch"] = float(stretch)
            output.append(record)

    # Stable source order is useful for nested LOD behavior and reproducibility.
    output.sort(key=lambda record: int(record.get("source_index", 0)))
    return output


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = foliage_assembly._generate_weeping_foliage
    foliage_assembly._generate_weeping_foliage = _generate_tuned_canopy
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    foliage_assembly._generate_weeping_foliage = _PREVIOUS_GENERATE
    _INSTALLED = False
