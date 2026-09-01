"""Continuous, density-aware weeping-willow foliage assembly.

This patch refines the v0.5 smart foliage system without changing its efficient
Geometry Nodes instancing architecture. Willow foliage is assembled as dense
pendulous curtains: card spacing is derived from actual source-card coverage,
successive sprig cards overlap by construction, and LOD thinning preserves an
evenly sampled 1D strand rather than punching random holes into it.
"""

import math

from mathutils import Vector

from . import foliage_assembly, foliage_assembly_lods, foliage_atlas_assembly, generator


_PREVIOUS_GENERATE_WEEPING = None
_PREVIOUS_DERIVE_WEEPING = None
_PREVIOUS_WEEPING_SPRIG = None
_PREVIOUS_PROFILE = None
_INSTALLED = False


_PROFILE_V2 = {
    "density": 0.92,
    "spacing": 0.52,
    "position_spread": 0.12,
    "twig": 0.20,
    "up": 0.0,
    "gravity": 1.0,
    "outward": 0.70,
    "jitter": math.radians(11.0),
    "width": 0.70,
    "height": 1.05,
    "source_aspect": 1.75,
    "role": 2,
    "strand_length_ratio": 0.30,
    "strand_count_per_meter": 0.95,
    "cards_per_meter": 3.20,
    "flutter": 0.030,
    "overlap": 0.62,
    "side_offset": 0.055,
    "max_strands_per_terminal": 8,
}


def _reference_card_length(settings, cfg, profile):
    """Approximate the world-space long-axis coverage of one source card."""
    base = float(settings.card_scale) * float(cfg["card_scale"])
    return max(
        float(settings.card_scale) * 0.45,
        base * float(profile["height"]) * float(profile["source_aspect"]),
    )


def _generate_weeping_v2(settings, terminals, cfg, profile, assembly):
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

    # Willow needs many nearby curtain anchors. Keep a spatial hash, but use it
    # to prevent exact duplicates rather than imposing broadleaf-like spacing.
    anchor_spacing = max(
        0.035,
        float(settings.card_scale)
        * float(profile["spacing"])
        * float(assembly.spacing),
    )
    anchor_grid = fa._AnchorGrid(anchor_spacing)
    lod_density = max(0.05, float(cfg["foliage"]))
    ground_z = max(0.03, float(settings.base_radius) * 0.18)

    overlap = fa._clamp(
        float(getattr(assembly, "willow_overlap", profile.get("overlap", 0.62))),
        0.20,
        0.88,
    )
    spacing_multiplier = max(0.55, float(assembly.willow_spacing))
    reference_length = _reference_card_length(settings, cfg, profile)
    target_step = max(
        float(settings.card_scale) * 0.14,
        reference_length * (1.0 - overlap) * spacing_multiplier,
    )

    for branch in terminals:
        if branch.get("dead", False) or len(branch.get("points", ())) < 2:
            continue

        branch_id = int(branch.get("id", 0))
        rng = fa._stable_rng(settings.seed, branch_id, 173)
        branch_length = generator._polyline_length(branch)

        raw_count = (
            branch_length
            * float(profile["strand_count_per_meter"])
            * float(settings.foliage_density)
            * float(profile["density"])
            * float(assembly.density_budget)
            * (lod_density ** 0.42)
        )
        strand_count = max(1, round(raw_count))
        # A substantial terminal shoot should not be represented by one lonely
        # curtain. This is still cheap because the leaves remain GN instances.
        if branch_length >= max(0.65, float(settings.card_scale) * 2.8):
            strand_count = max(2, strand_count)
        strand_count = min(int(profile.get("max_strands_per_terminal", 8)), strand_count)

        accepted_strands = 0
        attempts = max(strand_count * 5, 6)
        for _attempt in range(attempts):
            if accepted_strands >= strand_count:
                break

            # Spread curtains across the distal 2/3 of the terminal shoot. A
            # mild tip bias preserves the hanging outer silhouette without
            # stacking every strand at the exact terminal point.
            r = rng.random()
            f = 0.32 + 0.66 * (1.0 - (1.0 - r) ** 1.65)
            anchor, _radius, tangent = generator._point_on_polyline(branch, f)
            u, _v = generator._basis(tangent)
            anchor += u * rng.uniform(-0.11, 0.11) * float(settings.card_scale)
            if not anchor_grid.accept(anchor, anchor_spacing):
                continue

            strand_index = accepted_strands
            horizontal = Vector((tangent.x, tangent.y, 0.0))
            horizontal = fa._safe_normalized(horizontal, fa._outward_vector(anchor, tangent))
            outward = fa._outward_vector(anchor, tangent)
            side = fa._WORLD_UP.cross(horizontal)
            side = fa._safe_normalized(side, u)

            radial = math.hypot(anchor.x, anchor.y)
            radial_reference = max(
                float(settings.branch_length),
                float(settings.base_radius) * 4.0,
                1e-4,
            )
            exposure = fa._clamp(radial / radial_reference)
            desired = (
                float(settings.height)
                * float(profile["strand_length_ratio"])
                * float(assembly.willow_length)
                * (0.74 + 0.46 * exposure)
                * rng.uniform(0.82, 1.15)
            )
            available = max(0.25, anchor.z - ground_z)
            reach_cap = available * (
                0.55 + 0.45 * float(assembly.willow_ground_reach)
            )
            strand_length = max(
                reference_length * 1.35,
                min(desired, reach_cap),
            )

            # Coverage-based card count. Because count is ceil(length/step)+1,
            # the actual spacing can only be equal to or smaller than the
            # requested step, guaranteeing at least the requested overlap.
            required_count = max(3, int(math.ceil(strand_length / target_step)) + 1)
            max_cards = max(3, int(assembly.willow_max_cards))
            card_count = min(max_cards, required_count)

            # If a user sets a very low hard cap, keep the strand continuous by
            # shortening it rather than stretching large gaps between cards.
            if card_count < required_count:
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

                # Evaluate the strand derivative in world-distance terms so the
                # card long axis follows the hanging curve smoothly.
                distance_step = min(target_step * 0.35, strand_length * 0.08)
                t2 = fa._clamp(
                    (t * strand_length + distance_step)
                    / max(strand_length, 1e-5)
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

                # Alternate leaves around the hanging shoot, but keep the offset
                # small enough that neighboring sprig cards still visually join.
                alternate = -1.0 if card_i % 2 else 1.0
                p += (
                    side
                    * alternate
                    * float(settings.card_scale)
                    * float(profile.get("side_offset", 0.055))
                    * (1.0 - 0.18 * t)
                )

                long_axis = fa._safe_normalized(
                    local_dir * (0.90 * float(assembly.twig_alignment))
                    + fa._WORLD_DOWN * (0.62 * float(assembly.gravity_response)),
                    fa._WORLD_DOWN,
                )
                normal = outward + side * alternate * 0.16
                fan = (
                    rng.uniform(-1.0, 1.0)
                    * float(profile["jitter"])
                    * float(assembly.angular_jitter)
                )
                rotation = fa._card_rotation(long_axis, normal, fan)

                scale = fa._base_scale(settings, cfg, rng, profile)
                # Only a mild distal taper: v0.5 tapered too strongly, making
                # the bottom of a curtain visibly disconnect.
                taper = 1.0 - 0.11 * t
                scale *= taper
                scale.y *= 0.92
                scale.z *= 1.03

                source_local = strand_index * 1000 + card_i
                records.append(fa._record(
                    settings,
                    branch,
                    p,
                    rotation,
                    scale,
                    rng.randrange(atlas_count),
                    source_index,
                    source_local,
                    profile["role"],
                    strand_t=t,
                    strand_id=strand_global_id,
                ))
                source_index += 1

            accepted_strands += 1
            strand_global_id += 1

    return records


def _weeping_sprig_v2(profile, rng):
    """Create a denser continuous willow sprig in each generated atlas cell."""
    from . import procedural_pbr

    count = max(7, int(profile.get("leaf_count", 8)))
    aspect = max(float(profile.get("leaf_aspect", 4.45)), 1.0)
    leaves = []
    stem_base_y = -0.72

    for i in range(count):
        t = i / max(1, count - 1)
        y = -0.58 + 1.16 * t
        side = -1.0 if i % 2 else 1.0
        angle = side * rng.uniform(0.34, 0.58) + rng.uniform(-0.045, 0.045)
        sy = rng.uniform(0.18, 0.245)
        sx = sy / aspect
        cx = side * rng.uniform(0.050, 0.105)

        # All petioles share the same lower stem origin. The atlas rasterizer
        # draws twig segments from stem origin to leaf base, so these overlapping
        # segments produce a continuous central hanging shoot rather than a set
        # of disconnected leaf islands.
        leaves.append(procedural_pbr._leaf_record(
            cx,
            y,
            angle,
            sx,
            sy,
            profile["leaf_shape"],
            rng.uniform(-0.09, 0.09),
            0.0,
            stem_base_y,
        ))

    return leaves


def _strand_priority(cards):
    """Return a nested farthest-point order along one 1D strand."""
    ordered = sorted(cards, key=lambda r: float(r.get("strand_t", 0.0)))
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
                abs(t - float(ordered[s].get("strand_t", 0.0)))
                for s in selected
            )
            if distance > best_distance + 1e-9:
                best_distance = distance
                best_index = index
        selected.append(best_index)
        priority.append(ordered[best_index])
        remaining.remove(best_index)
    return priority


def _derive_weeping_v2(master_records, settings, lod):
    fal = foliage_assembly_lods
    cfg = generator.LOD[lod]
    factor = float(cfg["foliage"])
    if factor >= 0.999:
        return [fal._copy_record(record, 1.0) for record in master_records]

    # Keep more samples along surviving strands than v0.5.0. The expensive
    # dimension is strand/card count, not per-card geometry, because sources are
    # shared GN instances.
    strand_fraction = max(0.22, factor ** 0.44)
    card_fraction = max(0.34, factor ** 0.34)

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
        ranked_strands = sorted(
            strands.items(),
            key=lambda item: fal.stable_lods._stable_unit(
                int(settings.seed) ^ (branch_id * 0x45D9F3B),
                int(item[0]) * 37 + 17,
            ),
        )
        keep_strands = max(
            1,
            min(len(ranked_strands), round(len(ranked_strands) * strand_fraction)),
        )
        for _strand_id, cards in ranked_strands[:keep_strands]:
            priority = _strand_priority(cards)
            target_cards = max(
                2,
                min(len(priority), int(math.ceil(len(priority) * card_fraction))),
            )
            selected.extend(priority[:target_cards])

    if loose:
        selected.extend(fal._PREVIOUS_DERIVE(loose, settings, lod))

    # Dense structured curtains need little size inflation. Excessive LOD card
    # growth makes their individual rectangles obvious again.
    coverage = factor ** -0.12 if factor > 0.0 else 1.0
    scale_boost = min(1.45, max(float(cfg["card_scale"]), coverage))
    return [fal._copy_record(record, scale_boost) for record in selected]


def install():
    global _PREVIOUS_GENERATE_WEEPING, _PREVIOUS_DERIVE_WEEPING
    global _PREVIOUS_WEEPING_SPRIG, _PREVIOUS_PROFILE, _INSTALLED
    if _INSTALLED:
        return

    _PREVIOUS_GENERATE_WEEPING = foliage_assembly._generate_weeping_foliage
    _PREVIOUS_DERIVE_WEEPING = foliage_assembly_lods._derive_weeping
    _PREVIOUS_WEEPING_SPRIG = foliage_atlas_assembly._weeping_sprig
    _PREVIOUS_PROFILE = dict(foliage_assembly.ASSEMBLY_PROFILES["WEEPING"])

    foliage_assembly.ASSEMBLY_PROFILES["WEEPING"].update(_PROFILE_V2)
    foliage_assembly._generate_weeping_foliage = _generate_weeping_v2
    foliage_assembly_lods._derive_weeping = _derive_weeping_v2
    foliage_atlas_assembly._weeping_sprig = _weeping_sprig_v2
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    foliage_assembly._generate_weeping_foliage = _PREVIOUS_GENERATE_WEEPING
    foliage_assembly_lods._derive_weeping = _PREVIOUS_DERIVE_WEEPING
    foliage_atlas_assembly._weeping_sprig = _PREVIOUS_WEEPING_SPRIG
    foliage_assembly.ASSEMBLY_PROFILES["WEEPING"].clear()
    foliage_assembly.ASSEMBLY_PROFILES["WEEPING"].update(_PREVIOUS_PROFILE)
    _INSTALLED = False
