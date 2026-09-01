"""Efficient species-aware foliage card assembly.

The old foliage path placed a Cross/Tri bundle at each random point and then
randomized all three Euler angles.  That is cheap, but it creates the familiar
"box of cards" look and fails badly on pendulous species.

This module keeps the same Geometry Nodes instancing architecture, but changes
what each point means: one point is one atlas card with a parent-aware
orientation.  Volume comes from a controlled distribution of those instances,
not from stacking two or three coincident planes.
"""

import math
import random

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import generator, stable_lods


_PREVIOUS_GENERATE_FOLIAGE = None
_PREVIOUS_GENERATE_MASTER = None
_PREVIOUS_CREATE_SOURCES = None
_PREVIOUS_CREATE_POINTS = None
_INSTALLED = False

_WORLD_UP = Vector((0.0, 0.0, 1.0))
_WORLD_DOWN = Vector((0.0, 0.0, -1.0))


# These are card-assembly profiles, not botanical leaf-shape profiles.  The
# generated atlas already owns leaf/needle morphology; these profiles decide
# how those atlas clusters are distributed in 3D.
ASSEMBLY_PROFILES = {
    "BROADLEAF": {
        "density": 0.66,
        "spacing": 0.62,
        "position_spread": 0.42,
        "twig": 0.72,
        "up": 0.24,
        "gravity": 0.05,
        "outward": 0.82,
        "jitter": math.radians(28.0),
        "width": 0.92,
        "height": 0.84,
        "source_aspect": 1.00,
        "role": 0,
    },
    "AIRY": {
        "density": 0.52,
        "spacing": 0.78,
        "position_spread": 0.50,
        "twig": 0.82,
        "up": 0.20,
        "gravity": 0.07,
        "outward": 0.90,
        "jitter": math.radians(34.0),
        "width": 0.82,
        "height": 0.78,
        "source_aspect": 0.96,
        "role": 1,
    },
    "WEEPING": {
        "density": 0.62,
        "spacing": 1.12,
        "position_spread": 0.18,
        "twig": 0.24,
        "up": 0.0,
        "gravity": 0.94,
        "outward": 0.72,
        "jitter": math.radians(18.0),
        "width": 0.55,
        "height": 0.92,
        "source_aspect": 1.38,
        "role": 2,
        "strand_length_ratio": 0.245,
        "strand_count_per_meter": 0.48,
        "cards_per_meter": 1.55,
        "flutter": 0.045,
    },
    "CONIFER": {
        "density": 0.72,
        "spacing": 0.46,
        "position_spread": 0.30,
        "twig": 0.90,
        "up": 0.08,
        "gravity": 0.09,
        "outward": 0.48,
        "jitter": math.radians(32.0),
        "width": 0.74,
        "height": 0.92,
        "source_aspect": 1.20,
        "role": 3,
    },
    "COLUMNAR": {
        "density": 0.82,
        "spacing": 0.40,
        "position_spread": 0.22,
        "twig": 0.82,
        "up": 0.42,
        "gravity": 0.03,
        "outward": 0.38,
        "jitter": math.radians(24.0),
        "width": 0.66,
        "height": 0.98,
        "source_aspect": 1.25,
        "role": 4,
    },
}


AIRY_SPECIES = {
    "BIRCH", "ALDER", "ASPEN", "POPLAR", "JACARANDA", "ACACIA",
    "EUCALYPTUS", "WINDSWEPT", "SAPLING",
}
CONIFER_SPECIES = {"PINE", "STONE_PINE", "SPRUCE", "FIR", "CEDAR", "REDWOOD"}
COLUMNAR_SPECIES = {"CYPRESS"}


def _assembly_settings():
    scene = getattr(bpy.context, "scene", None)
    return getattr(scene, "trees2_foliage_assembly", None) if scene else None


def resolved_mode(settings, assembly=None):
    assembly = assembly or _assembly_settings()
    if assembly is not None and assembly.mode != "AUTO":
        return assembly.mode
    species = str(settings.species_preset)
    if species == "WILLOW":
        return "WEEPING"
    if species in CONIFER_SPECIES:
        return "CONIFER"
    if species in COLUMNAR_SPECIES:
        return "COLUMNAR"
    if species in AIRY_SPECIES:
        return "AIRY"
    return "BROADLEAF"


def effective_profile(settings, assembly=None):
    mode = resolved_mode(settings, assembly)
    profile = dict(ASSEMBLY_PROFILES.get(mode, ASSEMBLY_PROFILES["BROADLEAF"]))
    profile["mode"] = mode
    return profile


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _safe_normalized(vector, fallback):
    if vector.length_squared <= 1e-12:
        return fallback.copy()
    return vector.normalized()


def _outward_vector(position, tangent):
    outward = Vector((position.x, position.y, 0.0))
    if outward.length_squared > 1e-9:
        return outward.normalized()
    u, _v = generator._basis(tangent)
    return u.normalized()


def _card_rotation(long_axis, outward_normal, fan_angle=0.0):
    """Orient one SINGLE source card.

    Leaf-card local axes are X=plane normal, Y=horizontal, Z=long axis.  Build
    that basis directly instead of random Euler angles, which avoids the tall
    coincident slabs produced by the legacy path.
    """
    z_axis = _safe_normalized(long_axis, _WORLD_UP)
    x_axis = outward_normal - z_axis * outward_normal.dot(z_axis)
    if x_axis.length_squared <= 1e-9:
        x_axis, _unused = generator._basis(z_axis)
    else:
        x_axis.normalize()
    if abs(fan_angle) > 1e-8:
        x_axis = Quaternion(z_axis, fan_angle) @ x_axis
        x_axis.normalize()
    y_axis = z_axis.cross(x_axis)
    if y_axis.length_squared <= 1e-9:
        x_axis, y_axis = generator._basis(z_axis)
    else:
        y_axis.normalize()
    # Matrix() receives rows.  Transpose to make x/y/z the local basis columns.
    return Matrix((x_axis, y_axis, z_axis)).transposed().to_quaternion()


def _stable_rng(seed, branch_id, salt=0):
    mixed = (
        int(seed)
        ^ (int(branch_id) * 0x45D9F3B)
        ^ (int(salt) * 0x27D4EB2D)
        ^ 0x71A5C3D9
    ) & 0x7FFFFFFF
    return random.Random(mixed)


class _AnchorGrid:
    """Tiny O(n) average spatial hash used to avoid piles of overlapping cards."""

    def __init__(self, cell_size):
        self.cell_size = max(float(cell_size), 1e-4)
        self.cells = {}

    def _key(self, p):
        s = self.cell_size
        return (math.floor(p.x / s), math.floor(p.y / s), math.floor(p.z / s))

    def accept(self, p, minimum_distance):
        key = self._key(p)
        d2 = float(minimum_distance) ** 2
        for dz in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    for other in self.cells.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if (p - other).length_squared < d2:
                            return False
        self.cells.setdefault(key, []).append(p.copy())
        return True


def _base_scale(settings, cfg, rng, profile):
    random_factor = rng.uniform(
        max(0.15, 1.0 - float(settings.card_scale_randomness)),
        1.0 + float(settings.card_scale_randomness),
    )
    base = float(settings.card_scale) * float(cfg["card_scale"]) * random_factor
    return Vector((
        base * float(profile["width"]),
        base * float(profile["width"]),
        base * float(profile["height"]),
    ))


def _record(settings, branch, position, rotation, scale, atlas, source_index, local_index,
            role, strand_t=0.0, strand_id=-1):
    h = generator._clamp(position.z / max(float(settings.height), 1e-5))
    wind = h ** float(settings.wind_height_power)
    if role == 2:
        # Pendulous shoots get progressively more flexible toward the curtain tip.
        wind *= 0.82 + 0.30 * strand_t
        stiffness = generator._clamp(0.40 - wind * 0.30 - strand_t * 0.11)
    else:
        stiffness = generator._clamp(0.42 - wind * 0.32)
    return {
        "position": position,
        "rotation": rotation,
        "scale": scale,
        "atlas": atlas,
        "wind": wind,
        "phase": (float(branch.get("phase", 0.0)) + ((local_index * 0.173) % 0.31)) % 1.0,
        "stiffness": stiffness,
        "source_branch_id": int(branch.get("id", 0)),
        "source_local_index": int(local_index),
        "source_index": int(source_index),
        "assembly_role": int(role),
        "strand_t": float(strand_t),
        "strand_id": int(strand_id),
    }


def _biased_factor(rng, settings):
    r = rng.random()
    biased = 1.0 - (1.0 - r) ** (1.0 + float(settings.foliage_tip_bias) * 3.2)
    return float(settings.foliage_start) + (1.0 - float(settings.foliage_start)) * biased


def _cluster_orientation(settings, assembly, profile, rng, position, tangent):
    outward = _outward_vector(position, tangent)
    twig_weight = float(profile["twig"]) * float(assembly.twig_alignment)
    up_weight = float(profile["up"]) * (0.45 + float(settings.leaf_up_bias))
    gravity_weight = float(profile["gravity"]) * float(assembly.gravity_response)
    long_axis = tangent * twig_weight + _WORLD_UP * up_weight + _WORLD_DOWN * gravity_weight
    long_axis = _safe_normalized(long_axis, tangent)

    # The normal primarily faces outward from the crown, but a bounded fan
    # angle gives view-independent volume without coincident Cross/Tri planes.
    normal = outward * (float(profile["outward"]) * float(assembly.outward_bias))
    normal += generator._basis(tangent)[0] * rng.uniform(-0.22, 0.22)
    normal = _safe_normalized(normal, outward)
    fan = rng.uniform(-1.0, 1.0) * float(profile["jitter"]) * float(assembly.angular_jitter)
    return _card_rotation(long_axis, normal, fan)


def _generate_cluster_foliage(settings, terminals, cfg, profile, assembly):
    atlas_count = max(1, min(int(settings.atlas_variants), int(settings.atlas_columns) * int(settings.atlas_rows)))
    records = []
    source_index = 0
    min_spacing = max(0.025, float(settings.card_scale) * float(profile["spacing"]) * float(assembly.spacing))
    grid = _AnchorGrid(min_spacing)
    lod_density = float(cfg["foliage"])

    for branch in terminals:
        if branch.get("dead", False) or len(branch.get("points", ())) < 2:
            continue
        branch_id = int(branch.get("id", 0))
        rng = _stable_rng(settings.seed, branch_id, 19)
        length = generator._polyline_length(branch)
        target = max(1, round(
            length * 3.1 * float(settings.foliage_density)
            * float(profile["density"]) * float(assembly.density_budget) * lod_density
        ))
        accepted = 0
        # Rejection sampling is bounded so dense crowns cannot turn generation
        # into an expensive collision problem.
        attempts = max(target, target * 3)
        for attempt in range(attempts):
            if accepted >= target:
                break
            f = _biased_factor(rng, settings)
            p, _radius, tangent = generator._point_on_polyline(branch, f)
            u, v = generator._basis(tangent)
            envelope = (
                float(settings.card_scale) * float(settings.foliage_spread)
                * float(cfg["card_scale"]) * float(profile["position_spread"])
                * rng.uniform(0.18, 0.70)
            )
            p = p + u * rng.uniform(-envelope, envelope) + v * rng.uniform(-envelope, envelope)
            if accepted > 0 and not grid.accept(p, min_spacing):
                continue
            if accepted == 0:
                grid.accept(p, min_spacing)

            rotation = _cluster_orientation(settings, assembly, profile, rng, p, tangent)
            scale = _base_scale(settings, cfg, rng, profile)
            records.append(_record(
                settings, branch, p, rotation, scale,
                rng.randrange(atlas_count), source_index, accepted,
                profile["role"],
            ))
            accepted += 1
            source_index += 1
    return records


def _strand_position(anchor, horizontal, side, length, flutter, phase, t):
    # A short continuation of the parent twig transitions smoothly into a
    # gravity-dominated hanging shoot.  The lateral sine prevents ruler-straight
    # curtains while remaining cheap and deterministic.
    t = _clamp(t)
    forward = length * 0.16 * (1.0 - math.exp(-3.4 * t))
    drop = length * (0.12 * t + 0.88 * (t ** 1.12))
    sway = length * flutter * math.sin(phase + t * math.pi * 1.65) * math.sin(math.pi * t)
    return anchor + horizontal * forward + _WORLD_DOWN * drop + side * sway


def _generate_weeping_foliage(settings, terminals, cfg, profile, assembly):
    atlas_count = max(1, min(int(settings.atlas_variants), int(settings.atlas_columns) * int(settings.atlas_rows)))
    records = []
    source_index = 0
    strand_global_id = 0
    anchor_spacing = max(0.08, float(settings.card_scale) * float(profile["spacing"]) * float(assembly.spacing))
    anchor_grid = _AnchorGrid(anchor_spacing)
    lod_density = max(0.05, float(cfg["foliage"]))
    ground_z = max(0.03, float(settings.base_radius) * 0.18)

    for branch in terminals:
        if branch.get("dead", False) or len(branch.get("points", ())) < 2:
            continue
        branch_id = int(branch.get("id", 0))
        rng = _stable_rng(settings.seed, branch_id, 73)
        length = generator._polyline_length(branch)
        strand_count = max(1, round(
            length * float(profile["strand_count_per_meter"])
            * float(settings.foliage_density) * float(profile["density"])
            * float(assembly.density_budget) * (lod_density ** 0.58)
        ))
        strand_count = min(strand_count, 5)
        local_index = 0

        for strand_slot in range(strand_count * 3):
            if strand_slot >= strand_count and local_index > 0 and (local_index // 1000) >= strand_count:
                break
            if (local_index // 1000) >= strand_count:
                break
            f = 0.44 + 0.54 * (1.0 - (1.0 - rng.random()) ** 2.1)
            anchor, _radius, tangent = generator._point_on_polyline(branch, f)
            u, _v = generator._basis(tangent)
            small_offset = u * rng.uniform(-0.18, 0.18) * float(settings.card_scale)
            anchor = anchor + small_offset
            if not anchor_grid.accept(anchor, anchor_spacing):
                continue

            strand_index = local_index // 1000
            horizontal = Vector((tangent.x, tangent.y, 0.0))
            horizontal = _safe_normalized(horizontal, _outward_vector(anchor, tangent))
            outward = _outward_vector(anchor, tangent)
            side = _WORLD_UP.cross(horizontal)
            side = _safe_normalized(side, u)

            radial = math.hypot(anchor.x, anchor.y)
            radial_reference = max(float(settings.branch_length), float(settings.base_radius) * 4.0, 1e-4)
            exposure = _clamp(radial / radial_reference)
            desired = (
                float(settings.height) * float(profile["strand_length_ratio"])
                * float(assembly.willow_length) * (0.72 + 0.42 * exposure)
                * rng.uniform(0.76, 1.18)
            )
            available = max(0.25, anchor.z - ground_z)
            reach_cap = available * (0.58 + 0.42 * float(assembly.willow_ground_reach))
            strand_length = max(float(settings.card_scale) * 1.25, min(desired, reach_cap))

            spacing = max(
                float(settings.card_scale) * 0.78,
                1.0 / max(float(profile["cards_per_meter"]), 0.1),
            ) * float(assembly.willow_spacing)
            card_count = max(2, round(strand_length / max(spacing, 0.05)))
            card_count = min(int(assembly.willow_max_cards), card_count)
            card_count = max(2, round(card_count * (0.72 + 0.28 * (lod_density ** 0.45))))

            phase = rng.uniform(0.0, math.tau)
            flutter = float(profile["flutter"]) * float(assembly.willow_flutter)
            for card_i in range(card_count):
                t = (card_i + 0.18) / max(card_count - 0.64, 1.0)
                t = _clamp(t)
                p = _strand_position(anchor, horizontal, side, strand_length, flutter, phase, t)
                dt = min(0.025, 1.0 - t)
                p2 = _strand_position(anchor, horizontal, side, strand_length, flutter, phase, min(1.0, t + dt))
                local_dir = _safe_normalized(p2 - p, _WORLD_DOWN)

                # Willow leaves are alternate on pendulous shoots.  Alternating
                # a small lateral offset avoids a single opaque vertical strip.
                alternate = -1.0 if card_i % 2 else 1.0
                p += side * alternate * float(settings.card_scale) * 0.10 * (1.0 - 0.25 * t)
                long_axis = _safe_normalized(
                    local_dir * (0.82 * float(assembly.twig_alignment))
                    + _WORLD_DOWN * (0.48 * float(assembly.gravity_response)),
                    _WORLD_DOWN,
                )
                normal = outward + side * alternate * 0.28
                fan = rng.uniform(-1.0, 1.0) * float(profile["jitter"]) * float(assembly.angular_jitter)
                rotation = _card_rotation(long_axis, normal, fan)

                scale = _base_scale(settings, cfg, rng, profile)
                taper = 1.0 - 0.24 * t
                scale *= taper
                # Keep curtains fine: width shrinks more aggressively than
                # length, yielding narrow hanging foliage rather than card boxes.
                scale.x *= 0.88
                scale.y *= 0.88
                scale.z *= 1.04

                source_local = strand_index * 1000 + card_i
                records.append(_record(
                    settings, branch, p, rotation, scale,
                    rng.randrange(atlas_count), source_index, source_local,
                    profile["role"], strand_t=t, strand_id=strand_global_id,
                ))
                source_index += 1

            local_index = (strand_index + 1) * 1000
            strand_global_id += 1

    return records


def _generate_smart(settings, terminals, cfg):
    assembly = _assembly_settings()
    if assembly is None or not assembly.enabled:
        return None
    if str(settings.species_preset) == "DEAD_TREE" or float(settings.foliage_density) <= 0.0:
        return []
    profile = effective_profile(settings, assembly)
    if profile["mode"] == "WEEPING":
        return _generate_weeping_foliage(settings, terminals, cfg, profile, assembly)
    return _generate_cluster_foliage(settings, terminals, cfg, profile, assembly)


def _smart_generate_foliage(settings, terminals):
    records = _generate_smart(settings, terminals, generator.LOD[settings.lod])
    if records is None:
        return _PREVIOUS_GENERATE_FOLIAGE(settings, terminals)
    return records


def _smart_generate_master(settings, terminals):
    records = _generate_smart(settings, terminals, generator.LOD["LOD0"])
    if records is None:
        return _PREVIOUS_GENERATE_MASTER(settings, terminals)
    return records


def _smart_create_sources(source_collection, settings, leaf_material, suffix):
    assembly = _assembly_settings()
    if assembly is None or not assembly.enabled or not assembly.force_single_sources:
        return _PREVIOUS_CREATE_SOURCES(source_collection, settings, leaf_material, suffix)

    old_style = settings.card_style
    old_aspect = float(settings.card_aspect)
    try:
        settings.card_style = "SINGLE"
        generated = bool(settings.leaf_image and settings.leaf_image.get("trees2_generated_pbr", False))
        if generated and assembly.generated_atlas_aspect:
            settings.card_aspect = float(effective_profile(settings, assembly)["source_aspect"])
        return _PREVIOUS_CREATE_SOURCES(source_collection, settings, leaf_material, suffix)
    finally:
        settings.card_style = old_style
        settings.card_aspect = old_aspect


def _ensure_point_attribute(mesh, name, data_type, records, key, default):
    if len(mesh.vertices) != len(records):
        return
    attr = mesh.attributes.get(name)
    if attr is None:
        attr = mesh.attributes.new(name=name, type=data_type, domain="POINT")
    for item, record in zip(attr.data, records):
        value = record.get(key, default)
        if data_type == "FLOAT":
            item.value = float(value)
        else:
            item.value = int(value)


def _smart_create_points(collection, records, source_collection, settings, suffix):
    obj = _PREVIOUS_CREATE_POINTS(collection, records, source_collection, settings, suffix)
    assembly = _assembly_settings()
    if assembly is None or not assembly.enabled:
        return obj
    obj["trees2_foliage_assembly"] = resolved_mode(settings, assembly)
    obj["trees2_single_card_sources"] = bool(assembly.force_single_sources)
    if assembly.write_debug_attributes and records:
        _ensure_point_attribute(obj.data, "trees2_assembly_role", "INT", records, "assembly_role", 0)
        _ensure_point_attribute(obj.data, "trees2_source_branch_id", "INT", records, "source_branch_id", -1)
        _ensure_point_attribute(obj.data, "trees2_strand_id", "INT", records, "strand_id", -1)
        _ensure_point_attribute(obj.data, "trees2_strand_t", "FLOAT", records, "strand_t", 0.0)
    return obj


def install():
    global _PREVIOUS_GENERATE_FOLIAGE, _PREVIOUS_GENERATE_MASTER
    global _PREVIOUS_CREATE_SOURCES, _PREVIOUS_CREATE_POINTS, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE_FOLIAGE = generator.generate_foliage_points
    _PREVIOUS_GENERATE_MASTER = stable_lods.generate_master_foliage
    _PREVIOUS_CREATE_SOURCES = generator.create_leaf_sources
    _PREVIOUS_CREATE_POINTS = generator.create_leaf_points

    generator.generate_foliage_points = _smart_generate_foliage
    stable_lods.generate_master_foliage = _smart_generate_master
    generator.create_leaf_sources = _smart_create_sources
    generator.create_leaf_points = _smart_create_points
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_foliage_points = _PREVIOUS_GENERATE_FOLIAGE
    stable_lods.generate_master_foliage = _PREVIOUS_GENERATE_MASTER
    generator.create_leaf_sources = _PREVIOUS_CREATE_SOURCES
    generator.create_leaf_points = _PREVIOUS_CREATE_POINTS
    _INSTALLED = False
