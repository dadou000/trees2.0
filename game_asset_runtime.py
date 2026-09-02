"""Runtime metadata preparation for Trees 2.0 game-asset export.

The authoring tree remains two objects: wood and foliage points/instances.  This
module adds the persistent mapping required by a game runtime without changing
the visible tree:

* every wood vertex receives ``trees2_branch_t`` in addition to branch id;
* the final procedural branch graph is serialized on the tree root collection;
* every foliage point receives its support branch id and attachment factor;
* existing wind attributes remain untouched and can be exported alongside the
  runtime branch mapping.

The module is installed after all structural/foliage generator wrappers, so it
observes the final willow/general-tree topology rather than the generic base
skeleton.
"""

import json
import math

import bpy
from mathutils import Vector

from . import generator


_PREVIOUS_CREATE_BRANCH_MESH = None
_PREVIOUS_GENERATE_FOLIAGE = None
_PREVIOUS_CREATE_LEAF_POINTS = None
_INSTALLED = False


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _branch_lengths(branch):
    points = branch.get("points", ())
    cumulative = [0.0]
    total = 0.0
    for index in range(len(points) - 1):
        total += (points[index + 1][0] - points[index][0]).length
        cumulative.append(total)
    return cumulative, total


def _closest_factor_and_distance(branch, target):
    points = branch.get("points", ())
    if not points:
        return 0.0, float("inf")
    if len(points) == 1:
        return 0.0, (target - points[0][0]).length_squared

    cumulative, total = _branch_lengths(branch)
    if total <= 1.0e-9:
        return 0.0, (target - points[0][0]).length_squared

    best_distance = float("inf")
    best_length = 0.0
    for index in range(len(points) - 1):
        a = points[index][0]
        delta = points[index + 1][0] - a
        length_sq = delta.length_squared
        if length_sq <= 1.0e-12:
            local = 0.0
            projected = a
            segment_length = 0.0
        else:
            local = _clamp((target - a).dot(delta) / length_sq)
            projected = a + delta * local
            segment_length = math.sqrt(length_sq)
        distance = (target - projected).length_squared
        if distance < best_distance:
            best_distance = distance
            best_length = cumulative[index] + segment_length * local
    return _clamp(best_length / total), best_distance


def _vec3(value):
    return [float(value.x), float(value.y), float(value.z)]


def _branch_runtime_record(branch, by_id, settings):
    points = branch.get("points", ())
    branch_id = int(branch.get("id", -1))
    parent_id = int(branch.get("parent_id", -1))
    level = int(branch.get("level", 0))
    length = float(branch.get("length", generator._polyline_length(branch) if points else 0.0))

    attachment_t = 0.0
    if parent_id in by_id and points:
        attachment_t, _distance = _closest_factor_and_distance(by_id[parent_id], points[0][0])

    if len(points) >= 2:
        rest_direction = points[min(2, len(points) - 1)][0] - points[0][0]
        if rest_direction.length_squared <= 1.0e-12:
            rest_direction = points[1][0] - points[0][0]
        if rest_direction.length_squared > 1.0e-12:
            rest_direction.normalize()
        else:
            rest_direction = Vector((0.0, 0.0, 1.0))
    else:
        rest_direction = Vector((0.0, 0.0, 1.0))

    base_radius = float(points[0][1]) if points else 0.0
    tip_radius = float(points[-1][1]) if points else 0.0
    tree_radius = max(float(settings.base_radius), 1.0e-5)
    radius_ratio = max(base_radius / tree_radius, 1.0e-4)
    length_ratio = length / max(float(settings.height), 1.0e-5)

    # These are normalized runtime response hints rather than an attempt to
    # encode an exact wood Young's modulus.  The game can later replace them
    # with its own physical calibration while retaining deterministic geometry.
    stiffness = _clamp((radius_ratio ** 0.72) / (1.0 + length_ratio * 2.4 + level * 0.16), 0.025, 1.0)
    damping = _clamp(0.17 + level * 0.035 + stiffness * 0.05, 0.12, 0.42)
    frequency_hz = _clamp(0.22 + 5.0 * math.sqrt(stiffness) / math.sqrt(max(length, 0.30)), 0.16, 8.0)

    return {
        "id": branch_id,
        "parent_id": parent_id,
        "level": level,
        "dead": bool(branch.get("dead", False)),
        "attachment_t": float(attachment_t),
        "length": float(length),
        "base_radius": base_radius,
        "tip_radius": tip_radius,
        "phase": float(branch.get("phase", 0.0)),
        "rest_position": _vec3(points[0][0]) if points else [0.0, 0.0, 0.0],
        "rest_direction": _vec3(rest_direction),
        "stiffness": float(stiffness),
        "damping": float(damping),
        "natural_frequency_hz": float(frequency_hz),
        "centerline": [
            [float(point.x), float(point.y), float(point.z), float(radius)]
            for point, radius in points
        ],
    }


def _serialize_branch_graph(branches, settings):
    by_id = {int(branch.get("id", index)): branch for index, branch in enumerate(branches)}
    return {
        "schema": "trees2.branch_graph/1",
        "species": str(settings.species_preset),
        "seed": int(settings.seed),
        "lod": str(settings.lod),
        "height": float(settings.height),
        "base_radius": float(settings.base_radius),
        "branch_count": len(branches),
        "branches": [
            _branch_runtime_record(branch, by_id, settings)
            for branch in sorted(branches, key=lambda item: int(item.get("id", 0)))
        ],
    }


def _ensure_float_attribute(mesh, name, values):
    attr = mesh.attributes.get(name)
    if attr is not None and (attr.domain != "POINT" or attr.data_type != "FLOAT"):
        mesh.attributes.remove(attr)
        attr = None
    if attr is None:
        attr = mesh.attributes.new(name=name, type="FLOAT", domain="POINT")
    if len(attr.data) != len(values):
        return None
    for item, value in zip(attr.data, values):
        item.value = float(value)
    return attr


def _ensure_int_attribute(mesh, name, values):
    attr = mesh.attributes.get(name)
    if attr is not None and (attr.domain != "POINT" or attr.data_type != "INT"):
        mesh.attributes.remove(attr)
        attr = None
    if attr is None:
        attr = mesh.attributes.new(name=name, type="INT", domain="POINT")
    if len(attr.data) != len(values):
        return None
    for item, value in zip(attr.data, values):
        item.value = int(value)
    return attr


def _add_branch_t(mesh, branches):
    branch_id_attr = mesh.attributes.get("trees2_branch_id")
    if branch_id_attr is None or branch_id_attr.domain != "POINT":
        return False

    by_id = {int(branch.get("id", index)): branch for index, branch in enumerate(branches)}
    values = []
    for vertex, id_item in zip(mesh.vertices, branch_id_attr.data):
        branch = by_id.get(int(id_item.value))
        if branch is None:
            values.append(0.0)
            continue
        factor, _distance = _closest_factor_and_distance(branch, vertex.co)
        values.append(factor)
    return _ensure_float_attribute(mesh, "trees2_branch_t", values) is not None


def _create_branch_mesh_runtime(collection, branches, settings, bark_material, suffix):
    obj = _PREVIOUS_CREATE_BRANCH_MESH(collection, branches, settings, bark_material, suffix)
    mapped = _add_branch_t(obj.data, branches)
    graph = _serialize_branch_graph(branches, settings)
    collection["trees2_runtime_schema"] = 1
    collection["trees2_branch_graph"] = json.dumps(graph, separators=(",", ":"))
    obj["trees2_runtime_branch_mapping"] = bool(mapped)
    obj["trees2_runtime_branch_count"] = len(branches)
    return obj


def _nearest_terminal(position, terminals):
    best_branch = None
    best_factor = 0.0
    best_distance = float("inf")
    for branch in terminals:
        if len(branch.get("points", ())) < 2:
            continue
        factor, distance = _closest_factor_and_distance(branch, position)
        if distance < best_distance:
            best_distance = distance
            best_branch = branch
            best_factor = factor
    return best_branch, best_factor


def _enrich_foliage_records(settings, terminals, records):
    by_id = {int(branch.get("id", -1)): branch for branch in terminals}
    for record in records:
        position = record.get("position")
        if position is None:
            continue

        branch_id = record.get("source_branch_id")
        branch = by_id.get(int(branch_id)) if branch_id is not None else None
        factor = record.get("source_branch_t")

        if branch is not None:
            if factor is None:
                factor, _distance = _closest_factor_and_distance(branch, position)
        else:
            branch, factor = _nearest_terminal(position, terminals)
            if branch is not None:
                branch_id = int(branch.get("id", -1))

        record["source_branch_id"] = int(branch_id) if branch_id is not None else -1
        record["source_branch_t"] = float(factor if factor is not None else 0.0)
    return records


def _generate_foliage_runtime(settings, terminals):
    records = _PREVIOUS_GENERATE_FOLIAGE(settings, terminals)
    return _enrich_foliage_records(settings, terminals, records)


def _create_leaf_points_runtime(collection, records, source_collection, settings, suffix):
    obj = _PREVIOUS_CREATE_LEAF_POINTS(collection, records, source_collection, settings, suffix)
    if not records or len(obj.data.vertices) != len(records):
        obj["trees2_runtime_foliage_mapping"] = False
        return obj

    branch_ids = [int(record.get("source_branch_id", -1)) for record in records]
    branch_ts = [float(record.get("source_branch_t", 0.0)) for record in records]
    _ensure_int_attribute(obj.data, "trees2_source_branch_id", branch_ids)
    _ensure_float_attribute(obj.data, "trees2_source_branch_t", branch_ts)
    obj["trees2_runtime_foliage_mapping"] = True
    obj["trees2_runtime_foliage_count"] = len(records)
    return obj


def install():
    global _PREVIOUS_CREATE_BRANCH_MESH, _PREVIOUS_GENERATE_FOLIAGE
    global _PREVIOUS_CREATE_LEAF_POINTS, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_CREATE_BRANCH_MESH = generator.create_branch_mesh
    _PREVIOUS_GENERATE_FOLIAGE = generator.generate_foliage_points
    _PREVIOUS_CREATE_LEAF_POINTS = generator.create_leaf_points
    generator.create_branch_mesh = _create_branch_mesh_runtime
    generator.generate_foliage_points = _generate_foliage_runtime
    generator.create_leaf_points = _create_leaf_points_runtime
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.create_leaf_points = _PREVIOUS_CREATE_LEAF_POINTS
    generator.generate_foliage_points = _PREVIOUS_GENERATE_FOLIAGE
    generator.create_branch_mesh = _PREVIOUS_CREATE_BRANCH_MESH
    _INSTALLED = False
