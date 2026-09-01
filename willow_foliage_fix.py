"""Targeted weeping-willow foliage tuning.

The generic smart-foliage system remains responsible for instancing and export.
This module only replaces willow curtain placement and willow LOD selection.

The v3 model is deliberately canopy-aware:
* dense short/medium curtains fill the upper and middle crown,
* nearby strands are emitted as small curtain bundles instead of isolated hairs,
* long ground-reaching strands are sparse outer accents rather than the norm,
* low attachment points are strongly suppressed so density does not pile up
  around the lower trunk,
* willow card scale is nearly constant, matching the species' fairly consistent
  leaf size,
* the corrected atlas sprig from foliage_atlas_assembly remains authoritative.
"""

import math

from mathutils import Vector

from . import foliage_assembly, foliage_assembly_lods, generator


_PREVIOUS_GENERATE_WEEPING = None
_PREVIOUS_DERIVE_WEEPING = None
_PREVIOUS_PROFILE = None
_INSTALLED = False


_PROFILE_V3 = {
    "density": 1.08,
    "spacing": 0.40,
    "position_spread": 0.20,
    "twig": 0.20,
    "up": 0.0,
    "gravity": 1.0,
    "outward": 0.74,
    "jitter": math.radians(9.0),
    "width": 0.62,
    "height": 0.94,
    "source_aspect": 1.55,
    "role": 2,
    "strand_length_ratio": 0.235,
    "strand_count_per_meter": 1.30,
    "cards_per_meter": 3.8,
    "flutter": 0.038,
    "overlap": 0.68,
    "side_offset": 0.035,
    "max_bundles_per_terminal": 5,
    "max_bundle_size": 4,
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
        float(settings.card_scale) * 0.42,
        base * float(profile["height"]) * float(profile["source_aspect"]),
    )


def _height_density_weight(height_fraction):
    """Favor upper/mid crown attachments and strongly suppress the lower core."""
    h = _clamp(height_fraction)
    lower_gate = 0.16 + 0.84 * _smoothstep(0.27, 0.50, h)
    upper_fill = 0.72 + 0.62 * _smoothstep(0.43, 0.76, h)
    # Avoid an artificial cap of equal-length strands at the absolute tree top.
    top_softening = 1.0 - 0.18 * _smoothstep(0.90, 1.01, h)
    return lower_gate * upper_fill * top_softening


def _length_ratio_for_height(rng, height_fraction, exposure):
    """Mix short crown fill with medium drapes and sparse long outer accents."""
    h = _clamp(height_fraction)
    if h >= 0.75:
        ratio = rng.uniform(0.16, 0.235)
    elif h >= 0.50:
        ratio = rng.uniform(0.195, 0.285)
    else:
        ratio = rng.uniform(0.215, 0.305)

    ratio *= 0.92 + 0.17 * _clamp(exposure)
    accent_probability = 0.10 + 0.18 * _clamp(exposure)
    accent = rng.random() < accent_probability
    if accent:
        ratio *= rng.uniform(1.22, 1.42)
    return ratio, accent


def _willow_scale(settings, cfg, profile, rng):
    """Willow leaves stay nearly constant in scale; volume comes from placement."""
    base = float(settings.card_scale) * float(cfg["card_scale"])
    jitter = rng.uniform(0.965, 1.035)
    value = base * jitter
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
):
    fa = foliage_assembly
    h = _clamp(anchor.z / max(float(settings.height), 1.0e-5))
    ratio, accent = _length_ratio_for_height(rng, h, exposure)
    desired = (
        float(settings.height)
        * ratio
        * float(assembly.willow_length)
        * rng.uniform(0.94, 1.06)
    )

    available = max(0.25, anchor.z - ground_z)
    if accent:
        # A minority of exposed outer strands can form the characteristic long
        # willow fringe and approach the ground.
        reach_fraction = 0.72 + 0.27 * float(assembly.willow_ground_reach)
    else:
        # Most curtains stop well above the ground, building crown volume rather
        # than creating the uniform floor-length "hair" silhouette.
        reach_fraction = 0.54 + 0.31 * float(assembly.willow_ground_reach)
    reach_cap = available * reach_fraction
    strand_length = max(reference_length * 1.08, min(desired, reach_cap))

    required_count = max(3, int(math.ceil(strand_length / target_step)) + 1)
    max_cards = max(3, int(assembly.willow_max_cards))
    card_count = min(max_cards, required_count)
    if card_count < required_count:
        # Preserve overlap. A hard card budget shortens a strand rather than
        # stretching its cards apart.
        strand_length = min(strand_length, target_step * (card_count - 1))

    phase = rng.uniform(0.0, math.tau)
    flutter = float(profile["flutter"]) * float(assembly.willow_flutter)

    for card_i in range(card_count):
        t = card_i / max(card_count - 1, 1)
        p = fa._strand_position(
            anchor,
            horizontal,
            side,
            strand_length,
            flutter,
            phase,
            t,
        )

        distance_step = min(target_step * 0.35, strand_length * 0.075)
        t2 = fa._clamp(
            (t * strand_length + distance_step) / max(strand_length, 1.0e-5)
        )
        p2 = fa._strand_position(
            anchor,
            horizontal,
            side,
            strand_length,
            flutter,
            phase,
            t2,
        )
        local_dir = fa._safe_normalized(p2 - p, fa._WORLD_DOWN)

        # A tiny alternating side shift stops perfectly coincident cards without
        # turning the strand into a zig-zag chain.
        alternate = -1.0 if card_i % 2 else 1.0
        p += (
            side
            * alternate
            * float(settings.card_scale)
            * float(profile["side_offset"])
        )

        long_axis = fa._safe_normalized(
            local_dir * (0.92 * float(assembly.twig_alignment))
            + fa._WORLD_DOWN * (0.58 * float(assembly.gravity_response)),
            fa._WORLD_DOWN,
        )
        normal = outward + side * alternate * 0.12
        fan = (
            rng.uniform(-1.0, 1.0)
            * float(profile["jitter"])
            * float(assembly.angular_jitter)
        )
        rotation = fa._card_rotation(long_axis, normal, fan)

        scale = _willow_scale(settings, cfg, profile, rng)
        # Only 2% distal change: real willow blades do not become dramatically
        # smaller toward the bottom of a hanging shoot.
        scale *= 1.0 - 0.02 * t

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
        records.append(record)
        source_index += 1

    return source_index


def _generate_weeping_v3(settings, terminals, cfg, profile, assembly):
    fa = foliage_assembly
    atlas_count = max(
        1,
        min(
            int(settings.atlas_variants),
            int(settings.atlas_columns) * int(settings.atlas_rows),
        ),
    )
    records = []
    source_index = 0
    strand_global_id = 0

    # Separate bundle centres enough to fill canopy volume while allowing the
    # individual strands inside one bundle to overlap visually.
    anchor_spacing = max(
        0.060,
        float(settings.card_scale) * 0.22 * float(assembly.spacing),
    )
    anchor_grid = fa._AnchorGrid(anchor_spacing)
    lod_density = max(0.05, float(cfg["foliage"]))
    ground_z = max(0.03, float(settings.base_radius) * 0.18)

    overlap = fa._clamp(
        float(getattr(assembly, "willow_overlap", profile["overlap"])),
        0.30,
        0.88,
    )
    spacing_multiplier = max(0.55, float(assembly.willow_spacing))
    reference_length = _reference_card_length(settings, cfg, profile)
    target_step = max(
        float(settings.card_scale) * 0.12,
        reference_length * (1.0 - overlap) * spacing_multiplier,
    )

    for branch in terminals:
        if branch.get("dead", False) or len(branch.get("points", ())) < 2:
            continue

        branch_id = int(branch.get("id", 0))
        rng = fa._stable_rng(settings.seed, branch_id, 373)
        branch_length = generator._polyline_length(branch)

        # Think in bundles, not independent strings. The total number of strands
        # remains comparable to the old generator, but they form volumetric
        # curtain sheets in the crown instead of a uniformly spaced hair comb.
        raw_strands = (
            branch_length
            * float(profile["strand_count_per_meter"])
            * float(settings.foliage_density)
            * float(profile["density"])
            * float(assembly.density_budget)
            * (lod_density ** 0.40)
        )
        bundle_count = max(1, round(raw_strands / 2.6))
        bundle_count = min(int(profile["max_bundles_per_terminal"]), bundle_count)

        accepted_bundles = 0
        attempts = max(8, bundle_count * 7)
        for _attempt in range(attempts):
            if accepted_bundles >= bundle_count:
                break

            # Sample most of the terminal shoot rather than only its last few
            # percent. This fills the crown interior and hides radial scaffolds.
            r = rng.random()
            f = 0.20 + 0.78 * (1.0 - (1.0 - r) ** 1.28)
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
                float(settings.branch_length) * 1.08,
                float(settings.base_radius) * 4.0,
                1.0e-4,
            )
            exposure = _clamp(radial / radial_reference)
            density_weight = _height_density_weight(h) * (0.84 + 0.28 * exposure)
            if rng.random() > _clamp(density_weight, 0.10, 1.0):
                continue

            # Small random offset prevents different terminal branches from
            # landing their bundle centres at mathematically identical points.
            anchor += side * rng.uniform(-0.10, 0.10) * float(settings.card_scale)
            anchor += outward * rng.uniform(-0.045, 0.080) * float(settings.card_scale)
            if not anchor_grid.accept(anchor, anchor_spacing):
                continue

            bundle_size = 2
            if h >= 0.48:
                bundle_size += 1
            if h >= 0.68 and rng.random() < 0.68:
                bundle_size += 1
            if exposure < 0.30 and rng.random() < 0.45:
                bundle_size -= 1
            bundle_size = max(1, min(int(profile["max_bundle_size"]), bundle_size))

            bundle_spacing = float(settings.card_scale) * rng.uniform(0.14, 0.24)
            bundle_center = (bundle_size - 1) * 0.5
            for member in range(bundle_size):
                offset_index = member - bundle_center
                member_anchor = anchor.copy()
                member_anchor += side * offset_index * bundle_spacing
                member_anchor += outward * rng.uniform(-0.10, 0.13) * float(settings.card_scale)
                member_anchor += horizontal * rng.uniform(-0.05, 0.08) * float(settings.card_scale)
                member_anchor.z += rng.uniform(-0.035, 0.045) * float(settings.card_scale)

                # Each member gets a slightly different hanging plane, creating
                # depth and dark interior overlap without coincident geometry.
                member_side = fa._safe_normalized(
                    side + outward * rng.uniform(-0.13, 0.13),
                    side,
                )
                member_outward = fa._safe_normalized(
                    outward + side * rng.uniform(-0.12, 0.12),
                    outward,
                )
                member_horizontal = fa._safe_normalized(
                    horizontal + member_side * rng.uniform(-0.08, 0.08),
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
                    member,
                )
                strand_global_id += 1

            accepted_bundles += 1

    return records


def _strand_priority(cards):
    """Nested farthest-point order along a 1D strand for stable LOD thinning."""
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


def _derive_weeping_v3(master_records, settings, lod):
    fal = foliage_assembly_lods
    cfg = generator.LOD[lod]
    factor = float(cfg["foliage"])
    if factor >= 0.999:
        return [fal._copy_record(record, 1.0) for record in master_records]

    # Preserve willow volume more aggressively than generic foliage. Removing
    # entire curtain sheets too early is visually much more destructive than a
    # few extra shared card instances.
    strand_fraction = max(0.26, factor ** 0.36)
    card_fraction = max(0.38, factor ** 0.30)

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
        keep_strands = max(
            1,
            min(len(ranked), round(len(ranked) * strand_fraction)),
        )
        for _strand_id, cards in ranked[:keep_strands]:
            priority = _strand_priority(cards)
            target_cards = max(
                2,
                min(len(priority), int(math.ceil(len(priority) * card_fraction))),
            )
            selected.extend(priority[:target_cards])

    if loose:
        selected.extend(fal._PREVIOUS_DERIVE(loose, settings, lod))

    # Avoid inflating willow cards into obvious rectangles at low LOD.
    coverage = factor ** -0.10 if factor > 0.0 else 1.0
    scale_boost = min(1.30, max(1.0, coverage))
    return [fal._copy_record(record, scale_boost) for record in selected]


def install():
    global _PREVIOUS_GENERATE_WEEPING, _PREVIOUS_DERIVE_WEEPING
    global _PREVIOUS_PROFILE, _INSTALLED
    if _INSTALLED:
        return

    _PREVIOUS_GENERATE_WEEPING = foliage_assembly._generate_weeping_foliage
    _PREVIOUS_DERIVE_WEEPING = foliage_assembly_lods._derive_weeping
    _PREVIOUS_PROFILE = dict(foliage_assembly.ASSEMBLY_PROFILES["WEEPING"])

    foliage_assembly.ASSEMBLY_PROFILES["WEEPING"].update(_PROFILE_V3)
    foliage_assembly._generate_weeping_foliage = _generate_weeping_v3
    foliage_assembly_lods._derive_weeping = _derive_weeping_v3
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
