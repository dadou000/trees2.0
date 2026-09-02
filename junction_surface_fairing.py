"""Local post-Boolean surface fairing for branch junctions.

Exact Boolean produces watertight major forks, but the intersection can retain a
hard polygonal ridge where the two tube surfaces meet.  This wrapper runs after
``exact_junctions`` and applies a tiny bounded Laplacian relaxation only inside
major junction neighborhoods.

It deliberately does not remesh the tree and does not touch unrelated bark
surface areas.  Existing mesh attributes remain attached to the same vertices.
"""

import math

import bpy

from . import generator


_PREVIOUS_BRANCH_MESH = None
_INSTALLED = False


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _smoothstep01(value):
    t = _clamp(value)
    return t * t * (3.0 - 2.0 * t)


def _advanced_settings():
    scene = getattr(bpy.context, "scene", None)
    return getattr(scene, "trees2_advanced_settings", None) if scene else None


def _lod_index(lod):
    try:
        return int(str(lod).replace("LOD", ""))
    except Exception:
        return 0


def _junction_regions(branches, max_level):
    regions = []
    for branch in branches:
        level = int(branch.get("level", 0))
        points = branch.get("points", ())
        if level <= 0 or level > max_level or not points:
            continue
        if branch.get("willow_root_buttress", False):
            continue

        radius = max(float(points[0][1]), 1.0e-4)
        # Enough room to include the Boolean saddle and first child rings, but
        # not enough to round away the branch itself.
        influence = radius * (2.45 if level == 1 else 2.15)
        regions.append((points[0][0].copy(), influence, radius, level))
    return regions


def _adjacency(mesh):
    result = [set() for _ in mesh.vertices]
    for edge in mesh.edges:
        a, b = edge.vertices
        result[a].add(b)
        result[b].add(a)
    return result


def _weights(mesh, regions):
    weights = [0.0] * len(mesh.vertices)
    max_moves = [0.0] * len(mesh.vertices)
    for index, vertex in enumerate(mesh.vertices):
        point = vertex.co
        best_weight = 0.0
        best_radius = 0.0
        for center, influence, radius, level in regions:
            distance = (point - center).length
            if distance >= influence:
                continue
            t = 1.0 - distance / max(influence, 1.0e-6)
            # Keep the strongest relaxation near the actual saddle.  Level-2
            # junctions receive slightly less smoothing than primary forks.
            weight = _smoothstep01(t) * (1.0 if level == 1 else 0.82)
            if weight > best_weight:
                best_weight = weight
                best_radius = radius
        if best_weight > 0.0:
            weights[index] = best_weight
            max_moves[index] = max(best_radius * 0.075, 0.0005)
    return weights, max_moves


def _fair_mesh(mesh, regions):
    if not regions or not mesh.vertices or not mesh.edges:
        return 0

    adjacency = _adjacency(mesh)
    weights, max_moves = _weights(mesh, regions)
    affected = sum(1 for value in weights if value > 0.0)
    if affected == 0:
        return 0

    for _iteration in range(2):
        source = [vertex.co.copy() for vertex in mesh.vertices]
        targets = [None] * len(source)

        for index, weight in enumerate(weights):
            if weight <= 0.0 or not adjacency[index]:
                continue
            average = source[index].copy()
            average.zero()
            for neighbor in adjacency[index]:
                average += source[neighbor]
            average /= len(adjacency[index])

            delta = average - source[index]
            limit = max_moves[index]
            if delta.length > limit:
                delta.normalize()
                delta *= limit

            # Small factor by design: the pre-mesh branch-root blend does the
            # large-scale shaping; this pass only removes the Boolean ridge.
            targets[index] = source[index] + delta * (0.22 * weight)

        for index, target in enumerate(targets):
            if target is not None:
                mesh.vertices[index].co = target

    mesh.update(calc_edges=True)
    return affected


def _create_branch_mesh_faired(collection, branches, settings, bark_material, suffix):
    obj = _PREVIOUS_BRANCH_MESH(collection, branches, settings, bark_material, suffix)
    if obj is None or obj.type != "MESH":
        return obj

    advanced = _advanced_settings()
    if (
        not advanced
        or advanced.junction_mode != "EXACT_BOOLEAN"
        or _lod_index(settings.lod) > int(advanced.junction_boolean_lod_max)
        or obj.get("trees2_junction_mode") != "EXACT_BOOLEAN"
    ):
        return obj

    regions = _junction_regions(branches, int(advanced.junction_boolean_level_max))
    affected = _fair_mesh(obj.data, regions)
    if affected:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        obj["trees2_junction_surface_fairing"] = True
        obj["trees2_junction_surface_fairing_version"] = 1
        obj["trees2_junction_faired_vertices"] = int(affected)
    return obj


def install():
    global _PREVIOUS_BRANCH_MESH, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_BRANCH_MESH = generator.create_branch_mesh
    generator.create_branch_mesh = _create_branch_mesh_faired
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.create_branch_mesh = _PREVIOUS_BRANCH_MESH
    _INSTALLED = False
