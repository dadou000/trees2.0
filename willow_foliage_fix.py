"""Target-driven weeping-willow foliage assembly.

The generic smart-foliage system remains responsible for Geometry Nodes
instancing and export.  This module replaces only willow curtain placement and
willow LOD thinning.

V4 is tuned from direct comparison against a mature broad weeping-willow target:
* real terminal shoots create medium/long curtain sheets,
* virtual support branches supplied by willow_architecture create shorter fill
  branchlets along otherwise bare scaffold and secondary limbs,
* upper/middle crown density is deliberately high while the lower central core
  remains open,
* curtain members spread in both lateral and depth directions to build volume,
* very long floor-reaching strands are accents, not the dominant population,
* card size remains nearly constant across the tree.
"""

import math

from mathutils import Vector

from . import foliage_assembly, foliage_assembly_lods, generator


_PREVIOUS_GENERATE_WEEPING = None
_PREVIOUS_DERIVE_WEEPING = None
_PREVIOUS_PROFILE = None
_INSTALLED = False


_PROFILE_V4 = {
    "density": 1.20,
    "spacing": 0.34,
    "position_spread": 0.26,
    "twig": 0.20,
    "up": 0.0,
    "gravity": 1.0,
    "outward": 0.78,
    "jitter": math.radians(8.0),
    "width": 0.58,
    "height": 0.92,
    "source_aspect": 1.50,
    "role": 2,
    "strand_length_ratio": 0.225,
    "strand_count_per_meter": 1.55,
    "cards_per_meter": 4.1,
    "flutter": 0.040,
    "overlap": 0.70,
    "side_offset": 0.030,
    "max_bundles_per_terminal": 6,
    "max_bundle_size": 5,
}


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _smoothstep(lo, hi, value):
    if hi <= lo:
        return 1.0 if value >= hi else 0.0
    t = _clamp((value - lo) / (hi - lo))
    return t * t * (3.0 - 2.0 * t)


def _reference_card_length(settings, cfg, profile):
    base = float(settings.card_scale) * float(cfg["card_scale"])
    return max(
        float(settings.card_scale) * 0.40,
        base * float(profile["height"]) * float(profile["source_aspect"]),
    )


def _height_density_weight(height_fraction):
    """Dense crown shell from about 1/3 height upward, without a hard top cap."""
    h = _clamp(height_fraction)
    lower_gate = 0.12 + 0.88 * _smoothstep(0.24, 0.46, h)
    crown_fill = 0.88 + 0.78 * _smoothstep(0.39, 0.69, h)
    top_softening = 1.0 - 0.08 * _smoothstep(0.93, 1.01, h)
    return lower_gate * crown_fill * top_softening


def _length_ratio_for_height(rng, height_fraction, exposure):
    """Mostly short/medium drapes; sparse long exposed accents define the fringe."""
    h = _clamp(height_fraction)
    if h >= 0.76:
        ratio = rng.uniform(0.135, 0.205)
    elif h >= 0.52:
        ratio = rng.uniform(0.175, 0.255)
    else:
        ratio = rng.uniform(0.195, 0.285)

    ratio *= 0.94 + 0.14 * _clamp(exposure)
    accent_probability = 0.06 + 0.13 * _clamp(exposure)
    accent = rng.random() < accent_probability
    if accent:
        ratio *= rng.uniform(1.22, 1.38)
    return ratio, accent


def _willow_scale(settings, cfg, profile, rng):
    """Willow leaf/sprig scale is intentionally almost constant."""
    base = float(settings.card_scale) * float(cfg["card_scale"])
    value = base * rng.uniform(0.975, 1.025)
    return Vector((
        value * float(profile["width"]),
        value * float(profile["width"]),
        value * float(profile["height"]),
    ))


def _emit_strand(
    records,
    settings,
    cfg,
    profile,
    assembly,
    branch,
    rng,
    anchor,
    tangent,
    outward,
    side,
    horizontal,
    exposure,
    ground_z,
    target_step,
    reference_length,
    atlas_count,
    source_index,
    strand_global_id,
    local_strand_index,
    *,
    length_scale=1.0,
    allow_accent=True,
):
    fa = foliage_assembly
    h = _clamp(anchor.z / max(float(settings.height), 1.0e-5))
    ratio, accent = _length_ratio_for_height(rng, h, exposure)
    if not allow_accent:
        accent = False
        ratio = min(ratio, 0.235)
    ratio *= max(0.32, float(length_scale))

    desired = (
        float(settings.height)
        * ratio
        * float(assembly.willow_length)
        * rng.uniform(0.95, 1.05)
    )

    available = max(0.25, anchor.z - ground_z)
    if accent:
        reach_fraction = 0.73 + 0.26 * float(assembly.willow_ground_reach)
    elif allow_accent:
        reach_fraction = 0.53 + 0.30 * float(assembly.willow_ground_reach)
    else:
        # Virtual branchlets are crown-fill shoots; they should not become
        # floor-length hair hanging directly from a heavy scaffold.
        reach_fraction = 0.43 + 0.24 * float(assembly.willow_ground_reach)
    reach_cap = available * reach_fraction
    strand_length = max(reference_length * 1.03, min(desired, reach_cap))

    required_count = max(3, int(math.ceil(strand_length / target_step)) + 1)
    max_cards = max(3, int(assembly.willow_max_cards))
    card_count = min(max_cards, required_count)
    if card_count < required_count:
        strand_length = min(strand_length, target_step * (card_count - 1))

    phase = rng.uniform(0.0, math.tau)
    flutter = float(profile["flutter"]) * float(assembly.willow_flutter)

    for card_i in range(card_count):
        t = card_i / max(card_count - 1, 1)
        p = fa._strand_position(anchor, horizontal, side, strand_length, flutter, phase, t)

        distance_step = min(target_step * 0.34, strand_length * 0.072)
        t2 = fa._clamp((t * strand_length + distance_step) / max(strand_length, 1.0e-5))
        p2 = fa._strand_position(anchor, horizontal, side, strand_length, flutter, phase, t2)
        local_dir = fa._safe_normalized(p2 - p, fa._WORLD_DOWN)

        alternate = -1.0 if card_i % 2 else 1.0
        p += side * alternate * float(settings.card_scale) * float(profile["side_offset"])

        long_axis = fa._safe_normalized(
            local_dir * (0.93 * float(assembly.twig_alignment))
            + fa._WORLD_DOWN * (0.56 * float(assembly.gravity_response)),
            fa._WORLD_DOWN,
        )
        normal = outward + side * alternate * 0.11
        fan = (
            rng.uniform(-1.0, 1.0)
            * float(profile["jitter"])
            * float(assembly.angular_jitter)
        )
        rotation = fa._card_rotation(long_axis, normal, fan)

        scale = _willow_scale(settings, cfg, profile, rng)
        scale *= 1.0 - 0.015 * t

        record = fa._record(
            settings,
            branch,
            p,
            rotation,
            scale,
            rng.randrange(atlas_count),
            source_index,
            local_strand_index * 1000 + card_i,
            profile["role"],
            strand_t=t,
            strand_id=strand_global_id,
        )
        record["willow_accent_strand"] = bool(accent)
        record["willow_anchor_height"] = float(h)
        record["willow_virtual_anchor"] = bool(branch.get("willow_aux_anchor", False))
        records.append(record)
        source_index += 1

    return source_index


def _generate_weeping_v4(settings, terminals, cfg, profile, assembly):
    fa = foliage_assembly
    atlas_count = max(
        1,
        min(int(settings.atlas_variants), int(settings.atlas_columns) * int(settings.atlas_rows)),
    )
    records = []
    source_index = 0
    strand_global_id = 0

    anchor_spacing = max(
        0.045,
        float(settings.card_scale) * 0.18 * float(assembly.spacing),
    )
    anchor_grid = fa._AnchorGrid(anchor_spacing)
    lod_density = max(0.05, float(cfg["foliage"]))
    ground_z = max(0.03, float(settings.base_radius) * 0.18)

    overlap = fa._clamp(
        float(getattr(assembly, "willow_overlap", profile["overlap"])),
        0.34,
        0.90,
    )
    spacing_multiplier = max(0.52, float(assembly.willow_spacing))
    reference_length = _reference_card_length(settings, cfg, profile)
    target_step = max(
        float(settings.card_scale) * 0.105,
        reference_length * (1.0 - overlap) * spacing_multiplier,
    )

    for branch in terminals:
        if branch.get("dead", False) or len(branch.get("points", ())) < 2:
            continue

        branch_id = int(branch.get("id", 0))
        rng = fa._stable_rng(settings.seed, branch_id, 487)
        branch_length = generator._polyline_length(branch)
        virtual = bool(branch.get("willow_aux_anchor", False))
        anchor_weight = float(branch.get("willow_anchor_weight", 1.0)) if virtual else 1.0
        length_scale = float(branch.get("willow_length_scale", 1.0)) if virtual else 1.0
        fill_only = bool(branch.get("willow_fill_only", False))

        raw_strands = (
            branch_length
            * float(profile["strand_count_per_meter"])
            * float(settings.foliage_density)
            * float(profile["density"])
            * float(assembly.density_budget)
            * (lod_density ** 0.38)
            * anchor_weight
        )
        divisor = 1.75 if virtual else 2.15
        bundle_count = max(1, round(raw_strands / divisor))
        if not virtual and branch_length >= max(0.55, float(settings.card_scale) * 2.0):
            bundle_count = max(2, bundle_count)
        max_bundles = int(branch.get("willow_max_bundles", profile["max_bundles_per_terminal"]))
        bundle_count = min(max_bundles, bundle_count)

        accepted_bundles = 0
        attempts = max(10, bundle_count * 8)
        for _attempt in range(attempts):
            if accepted_bundles >= bundle_count:
                break

            r = rng.random()
            start_factor = 0.30 if virtual else 0.16
            f = start_factor + (0.985 - start_factor) * (1.0 - (1.0 - r) ** 1.20)
            anchor, _radius, tangent = generator._point_on_polyline(branch, f)
            u, _v = generator._basis(tangent)
            outward = fa._outward_vector(anchor, tangent)
            horizontal = Vector((tangent.x, tangent.y, 0.0))
            horizontal = fa._safe_normalized(horizontal, outward)
            side = fa._WORLD_UP.cross(horizontal)
            side = fa._safe_normalized(side, u)

            h = _clamp(anchor.z / max(float(settings.height), 1.0e-5))
            radial = math.hypot(anchor.x, anchor.y)
            radial_reference = max(
                float(settings.branch_length) * 1.10,
                float(settings.base_radius) * 4.0,
                1.0e-4,
            )
            exposure = _clamp(radial / radial_reference)
            density_weight = _height_density_weight(h) * (0.88 + 0.24 * exposure)
            if virtual:
                density_weight *= 0.96
            if rng.random() > _clamp(density_weight, 0.12, 1.0):
                continue

            # Wider 3D distribution than v3: target willow volume comes from
            # overlapping curtain sheets at different depths, not one thin shell.
            anchor += side * rng.uniform(-0.14, 0.14) * float(settings.card_scale)
            anchor += outward * rng.uniform(-0.08, 0.14) * float(settings.card_scale)
            if not anchor_grid.accept(anchor, anchor_spacing):
                continue

            if virtual:
                bundle_size = 2 + (1 if h >= 0.52 and rng.random() < 0.72 else 0)
                bundle_size = min(3, bundle_size)
            else:
                bundle_size = 3
                if h >= 0.44:
                    bundle_size += 1
                if h >= 0.64 and rng.random() < 0.72:
                    bundle_size += 1
                if exposure < 0.22 and rng.random() < 0.34:
                    bundle_size -= 1
                bundle_size = max(2, min(int(profile["max_bundle_size"]), bundle_size))

            bundle_spacing = float(settings.card_scale) * rng.uniform(0.18, 0.31)
            bundle_center = (bundle_size - 1) * 0.5
            for member in range(bundle_size):
                offset_index = member - bundle_center
                member_anchor = anchor.copy()
                member_anchor += side * offset_index * bundle_spacing
                member_anchor += outward * rng.uniform(-0.18, 0.22) * float(settings.card_scale)
                member_anchor += horizontal * rng.uniform(-0.09, 0.11) * float(settings.card_scale)
                member_anchor.z += rng.uniform(-0.055, 0.060) * float(settings.card_scale)

                member_side = fa._safe_normalized(
                    side + outward * rng.uniform(-0.20, 0.20),
                    side,
                )
                member_outward = fa._safe_normalized(
                    outward + side * rng.uniform(-0.18, 0.18),
                    outward,
                )
                member_horizontal = fa._safe_normalized(
                    horizontal + member_side * rng.uniform(-0.12, 0.12),
                    horizontal,
                )

                source_index = _emit_strand(
                    records,
                    settings,
                    cfg,
                    profile,
                    assembly,
                    branch,
                    rng,
                    member_anchor,
                    tangent,
                    member_outward,
                    member_side,
                    member_horizontal,
                    exposure,
                    ground_z,
                    target_step,
                    reference_length,
                    atlas_count,
                    source_index,
                    strand_global_id,
                    accepted_bundles * 10 + member,
                    length_scale=length_scale,
                    allow_accent=not fill_only,
                )
                strand_global_id += 1

            accepted_bundles += 1

    return records


def _strand_priority(cards):
    ordered = sorted(cards, key=lambda record: float(record.get("strand_t", 0.0)))
    if len(ordered) <= 2:
        return ordered

    selected = [0, len(ordered) - 1]
    priority = [ordered[0], ordered[-1]]
    remaining = set(range(1, len(ordered) - 1))
    while remaining:
        best_index = None
        best_distance = -1.0
        for index in remaining:
            t = float(ordered[index].get("strand_t", 0.0))
            distance = min(
                abs(t - float(ordered[selected_index].get("strand_t", 0.0)))
                for selected_index in selected
            )
            if distance > best_distance + 1.0e-9:
                best_distance = distance
                best_index = index
        selected.append(best_index)
        priority.append(ordered[best_index])
        remaining.remove(best_index)
    return priority


def _derive_weeping_v4(master_records, settings, lod):
    fal = foliage_assembly_lods
    cfg = generator.LOD[lod]
    factor = float(cfg["foliage"])
    if factor >= 0.999:
        return [fal._copy_record(record, 1.0) for record in master_records]

    strand_fraction = max(0.29, factor ** 0.32)
    card_fraction = max(0.41, factor ** 0.28)

    by_branch = {}
    loose = []
    for record in master_records:
        strand_id = int(record.get("strand_id", -1))
        if int(record.get("assembly_role", -1)) != 2 or strand_id < 0:
            loose.append(record)
            continue
        branch_id = int(record.get("source_branch_id", -1))
        by_branch.setdefault(branch_id, {}).setdefault(strand_id, []).append(record)

    selected = []
    for branch_id, strands in by_branch.items():
        ranked = sorted(
            strands.items(),
            key=lambda item: fal.stable_lods._stable_unit(
                int(settings.seed) ^ (branch_id * 0x45D9F3B),
                int(item[0]) * 37 + 17,
            ),
        )
        keep_strands = max(1, min(len(ranked), round(len(ranked) * strand_fraction)))
        for _strand_id, cards in ranked[:keep_strands]:
            priority = _strand_priority(cards)
            target_cards = max(
                2,
                min(len(priority), int(math.ceil(len(priority) * card_fraction))),
            )
            selected.extend(priority[:target_cards])

    if loose:
        selected.extend(fal._PREVIOUS_DERIVE(loose, settings, lod))

    coverage = factor ** -0.085 if factor > 0.0 else 1.0
    scale_boost = min(1.24, max(1.0, coverage))
    return [fal._copy_record(record, scale_boost) for record in selected]


def install():
    global _PREVIOUS_GENERATE_WEEPING, _PREVIOUS_DERIVE_WEEPING
    global _PREVIOUS_PROFILE, _INSTALLED
    if _INSTALLED:
        return

    _PREVIOUS_GENERATE_WEEPING = foliage_assembly._generate_weeping_foliage
    _PREVIOUS_DERIVE_WEEPING = foliage_assembly_lods._derive_weeping
    _PREVIOUS_PROFILE = dict(foliage_assembly.ASSEMBLY_PROFILES["WEEPING"])

    foliage_assembly.ASSEMBLY_PROFILES["WEEPING"].update(_PROFILE_V4)
    foliage_assembly._generate_weeping_foliage = _generate_weeping_v4
    foliage_assembly_lods._derive_weeping = _derive_weeping_v4
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    foliage_assembly._generate_weeping_foliage = _PREVIOUS_GENERATE_WEEPING
    foliage_assembly_lods._derive_weeping = _PREVIOUS_DERIVE_WEEPING
    foliage_assembly.ASSEMBLY_PROFILES["WEEPING"].clear()
    foliage_assembly.ASSEMBLY_PROFILES["WEEPING"].update(_PREVIOUS_PROFILE)
    _INSTALLED = False
