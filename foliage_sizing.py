import math

import bpy

from . import generator, stable_lods


_PREVIOUS_GENERATE_FOLIAGE = None
_PREVIOUS_GENERATE_MASTER = None
_PREVIOUS_CREATE_LEAF_POINTS = None
_INSTALLED = False


PROFILE_PRESETS = {
    "BROADLEAF": {
        "interior_scale": 1.16,
        "silhouette_scale": 0.72,
        "upper_crown_scale": 0.82,
        "edge_start": 0.58,
        "top_start": 0.72,
        "radial_influence": 1.00,
        "vertical_influence": 0.72,
        "crown_width_multiplier": 1.05,
        "min_multiplier": 0.42,
        "max_multiplier": 1.65,
    },
    "HEAVY": {
        "interior_scale": 1.22,
        "silhouette_scale": 0.64,
        "upper_crown_scale": 0.78,
        "edge_start": 0.56,
        "top_start": 0.70,
        "radial_influence": 1.06,
        "vertical_influence": 0.78,
        "crown_width_multiplier": 1.08,
        "min_multiplier": 0.38,
        "max_multiplier": 1.78,
    },
    "SLENDER": {
        "interior_scale": 1.11,
        "silhouette_scale": 0.74,
        "upper_crown_scale": 0.80,
        "edge_start": 0.60,
        "top_start": 0.70,
        "radial_influence": 0.94,
        "vertical_influence": 0.80,
        "crown_width_multiplier": 1.00,
        "min_multiplier": 0.44,
        "max_multiplier": 1.55,
    },
    "WILLOW": {
        "interior_scale": 1.10,
        "silhouette_scale": 0.68,
        "upper_crown_scale": 0.84,
        "edge_start": 0.54,
        "top_start": 0.76,
        "radial_influence": 1.08,
        "vertical_influence": 0.58,
        "crown_width_multiplier": 1.10,
        "min_multiplier": 0.38,
        "max_multiplier": 1.55,
    },
    "CONIFER": {
        "interior_scale": 1.06,
        "silhouette_scale": 0.80,
        "upper_crown_scale": 0.88,
        "edge_start": 0.62,
        "top_start": 0.76,
        "radial_influence": 0.82,
        "vertical_influence": 0.62,
        "crown_width_multiplier": 1.02,
        "min_multiplier": 0.52,
        "max_multiplier": 1.40,
    },
}


HEAVY_SPECIES = {
    "OAK", "HOLM_OAK", "CORK_OAK", "CHESTNUT", "WALNUT", "PLANE",
    "APPLE", "OLIVE", "BAOBAB",
}
SLENDER_SPECIES = {
    "BIRCH", "ALDER", "ASPEN", "POPLAR", "JACARANDA", "EUCALYPTUS",
}
WILLOW_SPECIES = {"WILLOW"}
CONIFER_SPECIES = {
    "PINE", "STONE_PINE", "SPRUCE", "FIR", "CEDAR", "CYPRESS", "REDWOOD",
}


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _smoothstep(edge0, edge1, value):
    if abs(edge1 - edge0) < 1e-8:
        return 1.0 if value >= edge1 else 0.0
    t = _clamp((value - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def _auto_profile_name(species):
    species = str(species)
    if species in HEAVY_SPECIES:
        return "HEAVY"
    if species in SLENDER_SPECIES:
        return "SLENDER"
    if species in WILLOW_SPECIES:
        return "WILLOW"
    if species in CONIFER_SPECIES:
        return "CONIFER"
    return "BROADLEAF"


def _custom_values(sizing):
    return {
        "interior_scale": float(sizing.interior_scale),
        "silhouette_scale": float(sizing.silhouette_scale),
        "upper_crown_scale": float(sizing.upper_crown_scale),
        "edge_start": float(sizing.edge_start),
        "top_start": float(sizing.top_start),
        "radial_influence": float(sizing.radial_influence),
        "vertical_influence": float(sizing.vertical_influence),
        "crown_width_multiplier": float(sizing.crown_width_multiplier),
        "min_multiplier": float(sizing.min_multiplier),
        "max_multiplier": float(sizing.max_multiplier),
    }


def effective_values(settings, sizing):
    mode = sizing.sizing_mode
    if mode == "AUTO":
        mode = _auto_profile_name(settings.species_preset)
    if mode == "CUSTOM":
        values = _custom_values(sizing)
    else:
        values = dict(PROFILE_PRESETS.get(mode, PROFILE_PRESETS["BROADLEAF"]))
    values["resolved_name"] = mode
    return values


def _position_multiplier(settings, sizing, position, values):
    """Return a card-scale multiplier from approximate sun/shade exposure.

    The procedural tree is local around the Z axis, so radial distance from Z
    is a useful canopy-depth estimate. The crown-shape function gives a local
    expected crown radius at the same height. This is deliberately independent
    of foliage RNG so the same point keeps the same size through all LODs.
    """
    height = max(float(settings.height), 1e-5)
    h = _clamp(float(position.z) / height)
    crown_start = _clamp(float(settings.branch_start), 0.0, 0.98)
    crown_h = _clamp((h - crown_start) / max(1.0 - crown_start, 1e-5))

    crown_profile = generator._crown_profile(
        settings.crown_shape,
        h,
        crown_start,
    )
    estimated_radius = max(
        float(settings.base_radius) * 1.5,
        float(settings.branch_length)
        * max(0.12, float(crown_profile))
        * values["crown_width_multiplier"],
    )
    radial = math.hypot(float(position.x), float(position.y)) / max(estimated_radius, 1e-5)

    edge_exposure = _smoothstep(values["edge_start"], 1.04, radial)
    edge_mix = _clamp(edge_exposure * values["radial_influence"])
    multiplier = (
        values["interior_scale"] * (1.0 - edge_mix)
        + values["silhouette_scale"] * edge_mix
    )

    upper_exposure = _smoothstep(values["top_start"], 1.0, crown_h)
    upper_mix = _clamp(upper_exposure * values["vertical_influence"])
    multiplier *= 1.0 + (values["upper_crown_scale"] - 1.0) * upper_mix

    # Position Influence blends the entire effect back toward uniform size.
    multiplier = 1.0 + (multiplier - 1.0) * float(sizing.strength)
    lo = min(values["min_multiplier"], values["max_multiplier"])
    hi = max(values["min_multiplier"], values["max_multiplier"])
    multiplier = max(lo, min(hi, multiplier))

    exposure = 1.0 - (1.0 - edge_mix) * (1.0 - upper_mix)
    return multiplier, exposure, radial, crown_h


def _apply_position_sizing(settings, records):
    scene = getattr(bpy.context, "scene", None)
    sizing = getattr(scene, "trees2_foliage_sizing", None) if scene else None
    if sizing is None or not sizing.enabled:
        return records

    values = effective_values(settings, sizing)
    for record in records:
        position = record.get("position")
        scale = record.get("scale")
        if position is None or scale is None:
            continue
        multiplier, exposure, radial, crown_h = _position_multiplier(
            settings,
            sizing,
            position,
            values,
        )
        record["scale"] = scale * multiplier
        record["location_scale"] = float(multiplier)
        record["canopy_exposure"] = float(exposure)
        record["canopy_radial"] = float(radial)
        record["canopy_height"] = float(crown_h)
        record["sizing_profile"] = values["resolved_name"]
    return records


def _sized_generate_foliage(settings, terminals):
    records = _PREVIOUS_GENERATE_FOLIAGE(settings, terminals)
    return _apply_position_sizing(settings, records)


def _sized_generate_master(settings, terminals):
    records = _PREVIOUS_GENERATE_MASTER(settings, terminals)
    return _apply_position_sizing(settings, records)


def _add_point_attribute(mesh, name, records, key, default=0.0):
    if len(mesh.vertices) != len(records):
        return
    attr = mesh.attributes.get(name)
    if attr is None:
        attr = mesh.attributes.new(name=name, type="FLOAT", domain="POINT")
    for item, record in zip(attr.data, records):
        item.value = float(record.get(key, default))


def _sized_create_leaf_points(collection, records, source_collection, settings, suffix):
    obj = _PREVIOUS_CREATE_LEAF_POINTS(
        collection,
        records,
        source_collection,
        settings,
        suffix,
    )
    if records and any("location_scale" in record for record in records):
        _add_point_attribute(obj.data, "trees2_location_scale", records, "location_scale", 1.0)
        _add_point_attribute(obj.data, "trees2_canopy_exposure", records, "canopy_exposure", 0.0)
        _add_point_attribute(obj.data, "trees2_canopy_radial", records, "canopy_radial", 0.0)
        _add_point_attribute(obj.data, "trees2_canopy_height", records, "canopy_height", 0.0)
        scene = getattr(bpy.context, "scene", None)
        sizing = getattr(scene, "trees2_foliage_sizing", None) if scene else None
        if sizing is not None:
            values = effective_values(settings, sizing)
            obj["trees2_foliage_sizing"] = values["resolved_name"]
            obj["trees2_position_size_strength"] = float(sizing.strength)
    return obj


def install():
    global _PREVIOUS_GENERATE_FOLIAGE, _PREVIOUS_GENERATE_MASTER
    global _PREVIOUS_CREATE_LEAF_POINTS, _INSTALLED
    if _INSTALLED:
        return

    _PREVIOUS_GENERATE_FOLIAGE = generator.generate_foliage_points
    _PREVIOUS_GENERATE_MASTER = stable_lods.generate_master_foliage
    _PREVIOUS_CREATE_LEAF_POINTS = generator.create_leaf_points

    generator.generate_foliage_points = _sized_generate_foliage
    stable_lods.generate_master_foliage = _sized_generate_master
    generator.create_leaf_points = _sized_create_leaf_points
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_foliage_points = _PREVIOUS_GENERATE_FOLIAGE
    stable_lods.generate_master_foliage = _PREVIOUS_GENERATE_MASTER
    generator.create_leaf_points = _PREVIOUS_CREATE_LEAF_POINTS
    _INSTALLED = False
