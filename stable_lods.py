import json
import math
import random

import bpy
from mathutils import Vector

from . import generator


def _copy_branch(branch):
    copied = dict(branch)
    copied["points"] = [(p.copy(), float(r)) for p, r in branch["points"]]
    return copied


def _stable_unit(seed, value):
    """Deterministic 0..1 hash used for nested LOD selection."""
    x = (int(value) ^ int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def _branch_score(branch, seed):
    points = branch.get("points", ())
    if not points:
        return 0.0
    radius = max(float(points[0][1]), 1e-6)
    length = float(branch.get("length", generator._polyline_length(branch)))
    jitter = 0.82 + 0.36 * _stable_unit(seed, branch.get("id", 0) * 37 + 11)
    return radius * radius * max(length, 0.001) * jitter


def _resample_branch(branch, segment_factor, minimum_segments=2):
    copied = _copy_branch(branch)
    original_segments = max(1, len(branch["points"]) - 1)
    target_segments = max(minimum_segments, round(original_segments * segment_factor))
    target_segments = min(original_segments, target_segments)
    if target_segments >= original_segments:
        return copied

    points = []
    for i in range(target_segments + 1):
        factor = i / target_segments
        p, radius, _tangent = generator._point_on_polyline(branch, factor)
        points.append((p.copy(), float(radius)))
    copied["points"] = points
    copied["length"] = generator._polyline_length(copied)
    return copied


def derive_lod_skeleton(master_branches, settings, lod):
    """Create a nested LOD from one LOD0 skeleton.

    The trunk is unconditional. Child branches are selected per parent from a
    stable importance ranking, so LOD2 is a subset of LOD1 rather than a newly
    randomized tree.
    """
    cfg = generator.LOD[lod]
    if not master_branches:
        return [], []

    master_by_id = {int(b.get("id", 0)): b for b in master_branches}
    trunk = master_by_id.get(0)
    if trunk is None:
        trunk = min(master_branches, key=lambda b: (b.get("level", 0), b.get("id", 0)))

    children_by_parent = {}
    for branch in master_branches:
        if branch is trunk:
            continue
        children_by_parent.setdefault(int(branch.get("parent_id", -1)), []).append(branch)

    selected_ids = {int(trunk.get("id", 0))}
    selected_master = [trunk]
    max_levels = min(int(settings.branch_levels), int(cfg["max_levels"]))
    factor = float(cfg["branch_factor"])

    frontier = [trunk]
    for level in range(1, max_levels + 1):
        next_frontier = []
        for parent in frontier:
            children = [
                b for b in children_by_parent.get(int(parent.get("id", -1)), ())
                if int(b.get("level", level)) == level
            ]
            if not children:
                continue

            # Top-K from a fixed ranking makes every lower LOD a strict subset.
            ranked = sorted(
                children,
                key=lambda b: (_branch_score(b, settings.seed), -int(b.get("id", 0))),
                reverse=True,
            )
            keep_count = max(1, min(len(ranked), round(len(ranked) * factor)))
            # Keep at least two primary limbs when the source has them. This is
            # important for silhouette continuity at LOD2/LOD3.
            if level == 1 and len(ranked) >= 2:
                keep_count = max(2, keep_count)

            kept = ranked[:keep_count]
            for branch in kept:
                branch_id = int(branch.get("id", 0))
                if branch_id in selected_ids:
                    continue
                selected_ids.add(branch_id)
                selected_master.append(branch)
                if not branch.get("dead", False):
                    next_frontier.append(branch)
        frontier = next_frontier
        if not frontier:
            break

    # Preserve hierarchy order and simplify only the polyline sampling.
    selected_master.sort(key=lambda b: (int(b.get("level", 0)), int(b.get("id", 0))))
    derived = []
    for branch in selected_master:
        level = int(branch.get("level", 0))
        minimum = 6 if level == 0 and lod == "LOD1" else 4 if level == 0 else 2
        derived.append(_resample_branch(branch, float(cfg["segment_factor"]), minimum))

    living_child_ids = {}
    for branch in derived:
        if branch.get("dead", False):
            continue
        parent = int(branch.get("parent_id", -1))
        living_child_ids.setdefault(parent, []).append(int(branch.get("id", 0)))

    terminals = [
        branch for branch in derived
        if int(branch.get("level", 0)) > 0
        and not branch.get("dead", False)
        and not living_child_ids.get(int(branch.get("id", 0)))
    ]
    if not terminals:
        terminals = [b for b in derived if int(b.get("level", 0)) > 0 and not b.get("dead", False)] or [derived[0]]
    return derived, terminals


def generate_master_foliage(settings, terminals):
    """Generate the full foliage population once, at LOD0 density."""
    rng = random.Random(settings.seed ^ 0x5F3759DF)
    cfg = generator.LOD["LOD0"]
    atlas_count = max(1, min(settings.atlas_variants, settings.atlas_columns * settings.atlas_rows))
    records = []
    source_index = 0

    for branch in terminals:
        if branch.get("dead", False) or len(branch.get("points", ())) < 2:
            continue
        length = generator._polyline_length(branch)
        count = max(1, round(length * 3.1 * settings.foliage_density))
        branch_id = int(branch.get("id", 0))
        for local_index in range(count):
            r = rng.random()
            biased = 1.0 - (1.0 - r) ** (1.0 + settings.foliage_tip_bias * 3.2)
            f = settings.foliage_start + (1.0 - settings.foliage_start) * biased
            p, _, tangent = generator._point_on_polyline(branch, f)
            u, v = generator._basis(tangent)
            envelope = settings.card_scale * settings.foliage_spread * rng.uniform(0.18, 0.72)
            p = p + u * rng.uniform(-envelope, envelope) + v * rng.uniform(-envelope, envelope)
            q, scale = generator._leaf_transform(rng, settings, cfg)
            h = generator._clamp(p.z / max(settings.height, 1e-5))
            wind = h ** settings.wind_height_power
            records.append({
                "position": p,
                "rotation": q,
                "scale": scale,
                "atlas": rng.randrange(atlas_count),
                "wind": wind,
                "phase": (branch.get("phase", 0.0) + rng.uniform(-0.18, 0.18)) % 1.0,
                "stiffness": generator._clamp(0.42 - wind * 0.32),
                "source_branch_id": branch_id,
                "source_local_index": local_index,
                "source_index": source_index,
            })
            source_index += 1
    return records


def derive_lod_foliage(master_records, settings, lod):
    """Spatially stable, per-cluster foliage thinning.

    Each source terminal keeps the same proportional share, preventing one
    branch from becoming bare while another stays dense merely due to RNG.
    """
    cfg = generator.LOD[lod]
    factor = float(cfg["foliage"])
    if factor >= 0.999:
        keep = list(master_records)
    else:
        groups = {}
        for record in master_records:
            groups.setdefault(int(record.get("source_branch_id", -1)), []).append(record)
        keep = []
        for branch_id, group in groups.items():
            ranked = sorted(
                group,
                key=lambda r: _stable_unit(
                    settings.seed ^ (branch_id * 0x45D9F3B),
                    int(r.get("source_local_index", r.get("source_index", 0))),
                ),
            )
            count = max(1, min(len(ranked), round(len(ranked) * factor)))
            keep.extend(ranked[:count])

    # Compensate projected canopy coverage as card count drops. The exponent is
    # intentionally softer than exact area conservation to avoid giant cards.
    if factor > 0.0:
        coverage_scale = factor ** -0.38
    else:
        coverage_scale = 1.0
    scale_boost = min(2.45, max(float(cfg["card_scale"]), coverage_scale))

    derived = []
    for record in keep:
        copied = dict(record)
        copied["position"] = record["position"].copy()
        copied["rotation"] = record["rotation"].copy()
        copied["scale"] = record["scale"].copy() * scale_boost
        derived.append(copied)
    return derived


def build_tree_from_data(context, settings, branches, terminals, records, location=None):
    """Build a normal Trees2 collection from pre-derived LOD data."""
    suffix = generator._safe_name(settings.seed, settings.lod)
    root = bpy.data.collections.new(f"Trees2_Tree_{suffix}")
    context.scene.collection.children.link(root)
    sources = bpy.data.collections.new(f"Trees2_Sources_{suffix}")
    root.children.link(sources)
    sources["trees2_internal"] = True

    bark_material = generator.create_bark_material(settings, suffix)
    leaf_material = generator.create_leaf_material(settings, suffix)
    branch_obj = generator.create_branch_mesh(root, branches, settings, bark_material, suffix)
    generator.create_leaf_sources(sources, settings, leaf_material, suffix)
    foliage_obj = generator.create_leaf_points(root, records, sources, settings, suffix)

    tree_location = Vector(location) if location is not None else context.scene.cursor.location.copy()
    branch_obj.location = tree_location
    foliage_obj.location = tree_location

    root["trees2_tree"] = True
    root["trees2_suffix"] = suffix
    root["trees2_seed"] = settings.seed
    root["trees2_lod"] = settings.lod
    root["trees2_settings"] = json.dumps(generator._settings_snapshot(settings))
    root["trees2_lod_source"] = "LOD0_MASTER"
    root["trees2_lod_branch_factor"] = float(generator.LOD[settings.lod]["branch_factor"])
    root["trees2_lod_foliage_factor"] = float(generator.LOD[settings.lod]["foliage"])

    for obj in (branch_obj, foliage_obj):
        obj["trees2_root_collection"] = root.name
        obj["trees2_suffix"] = suffix
        obj["trees2_lod_source"] = "LOD0_MASTER"

    branch_obj["trees2_branch_count"] = len(branches)
    branch_obj["trees2_terminal_count"] = len(terminals)
    branch_obj["trees2_leaf_points"] = len(records)
    branch_obj["trees2_dead_branches"] = sum(1 for b in branches if b.get("dead", False))
    branch_obj["trees2_triangle_estimate"] = sum(len(p.vertices) - 2 for p in branch_obj.data.polygons)

    bpy.ops.object.select_all(action="DESELECT")
    branch_obj.hide_set(False)
    branch_obj.select_set(True)
    context.view_layer.objects.active = branch_obj
    return root, branch_obj, foliage_obj
