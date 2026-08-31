import math
import random

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

from . import generator


_ORIGINAL_GENERATE = None
_ORIGINAL_POLYLINE = None
_ORIGINAL_BRANCH_MESH = None
_ORIGINAL_BARK_MATERIAL = None
_ACTIVE_FIELD = None
_INSTALLED = False


def _lod_index(lod):
    try:
        return int(str(lod).replace("LOD", ""))
    except Exception:
        return 0


def _advanced_settings():
    scene = getattr(bpy.context, "scene", None)
    return getattr(scene, "trees2_advanced_settings", None) if scene else None


class CanopyCompetitionField:
    """Space-colonization field shared while one tree skeleton grows."""

    def __init__(self, settings, advanced):
        self.settings = settings
        self.advanced = advanced
        self.rng = random.Random(settings.seed ^ 0x7A17C011)
        self.attractors = []
        self.occupied = {}
        self.cell_size = max(advanced.competition_clearance, settings.base_radius * 0.22, 0.05)
        self._sample_attractors()
        self._seed_trunk_occupancy()

    def _cell(self, p):
        s = self.cell_size
        return (math.floor(p.x / s), math.floor(p.y / s), math.floor(p.z / s))

    def _insert_occupied(self, p, radius):
        key = self._cell(p)
        self.occupied.setdefault(key, []).append((p.copy(), max(radius, 0.001)))

    def _query_occupied(self, p, distance):
        s = self.cell_size
        n = max(1, int(math.ceil(distance / s)))
        cx, cy, cz = self._cell(p)
        for x in range(cx - n, cx + n + 1):
            for y in range(cy - n, cy + n + 1):
                for z in range(cz - n, cz + n + 1):
                    for item in self.occupied.get((x, y, z), ()):
                        yield item

    def _sample_attractors(self):
        count = max(32, round(self.advanced.attraction_points * generator.LOD[self.settings.lod]["branch_factor"]))
        start = self.settings.branch_start
        max_radius = max(self.settings.branch_length * 1.18, self.settings.base_radius * 3.0)
        for _ in range(count):
            zf = self.rng.uniform(start, 1.02)
            profile = generator._crown_profile(self.settings.crown_shape, min(zf, 1.0), start)
            radius = max_radius * profile
            r = radius * math.sqrt(self.rng.random())
            a = self.rng.uniform(0.0, math.tau)
            jitter_z = self.rng.uniform(-0.035, 0.035) * self.settings.height
            self.attractors.append(Vector((math.cos(a) * r, math.sin(a) * r, zf * self.settings.height + jitter_z)))

    def _seed_trunk_occupancy(self):
        samples = max(12, int(self.settings.height / max(self.cell_size * 0.8, 0.08)))
        for i in range(samples + 1):
            t = i / samples
            z = self.settings.height * t
            radius = self.settings.base_radius * max(0.025, (1.0 - t) ** self.settings.trunk_taper)
            self._insert_occupied(Vector((0.0, 0.0, z)), radius)

    def attraction(self, position, forward):
        influence = self.advanced.attraction_influence
        influence_sq = influence * influence
        accum = Vector((0.0, 0.0, 0.0))
        total = 0.0
        for target in self.attractors:
            delta = target - position
            d2 = delta.length_squared
            if d2 <= 1e-10 or d2 > influence_sq:
                continue
            distance = math.sqrt(d2)
            direction = delta / distance
            facing = direction.dot(forward)
            if facing < -0.28:
                continue
            weight = (1.0 - distance / influence) ** 2 * (0.55 + 0.45 * max(0.0, facing))
            accum += direction * weight
            total += weight
        if total <= 1e-8 or accum.length_squared <= 1e-10:
            return Vector((0.0, 0.0, 0.0))
        return accum.normalized()

    def avoidance(self, position, radius, branch_start):
        clearance = self.advanced.competition_clearance + radius
        accum = Vector((0.0, 0.0, 0.0))
        for occupied, occupied_radius in self._query_occupied(position, clearance + self.settings.base_radius):
            if (occupied - branch_start).length < max(radius * 3.0, self.settings.base_radius * 0.55):
                continue
            delta = position - occupied
            distance = delta.length
            desired = clearance + occupied_radius
            if distance <= 1e-8 or distance >= desired:
                continue
            accum += delta.normalized() * ((desired - distance) / desired) ** 2
        if accum.length_squared <= 1e-10:
            return Vector((0.0, 0.0, 0.0))
        return accum.normalized()

    def collision_cost(self, position, radius, branch_start):
        clearance = self.advanced.competition_clearance * 0.72 + radius
        cost = 0.0
        for occupied, occupied_radius in self._query_occupied(position, clearance + self.settings.base_radius):
            if (occupied - branch_start).length < max(radius * 3.0, self.settings.base_radius * 0.55):
                continue
            distance = (position - occupied).length
            desired = clearance + occupied_radius
            if distance < desired:
                cost += (desired - distance) / max(desired, 1e-6)
        return cost

    def add_segment(self, a, b, radius):
        length = (b - a).length
        spacing = max(self.cell_size * 0.62, radius * 0.7, 0.025)
        count = max(1, int(math.ceil(length / spacing)))
        for i in range(1, count + 1):
            self._insert_occupied(a.lerp(b, i / count), radius)

        kill = self.advanced.attraction_kill_distance + radius * 0.35
        kill_sq = kill * kill
        self.attractors = [target for target in self.attractors if (target - b).length_squared > kill_sq]


def _competitive_polyline(rng, start, direction, length, base_radius, segments, bend, droop, upward, collar=0.0):
    field = _ACTIVE_FIELD
    if field is None:
        return _ORIGINAL_POLYLINE(rng, start, direction, length, base_radius, segments, bend, droop, upward, collar)

    advanced = field.advanced
    points = []
    pos = start.copy()
    d = direction.normalized()
    step = length / max(segments, 1)

    for i in range(segments + 1):
        t = i / max(segments, 1)
        radius = max(base_radius * (1.0 - t) ** 1.34, base_radius * 0.035)
        if i == 0:
            radius *= 1.0 + collar
        elif i == 1:
            radius *= 1.0 + collar * 0.24
        points.append((pos.copy(), radius))
        if i == segments:
            break

        jitter = Vector((rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(-0.50, 0.50))) * bend * (0.075 + t * 0.030)
        gravity = Vector((0.0, 0.0, -droop * (0.010 + t * 0.055)))
        light = Vector((0.0, 0.0, upward * (0.008 + t * 0.018)))
        attract = field.attraction(pos, d)
        avoid = field.avoidance(pos, radius, start)

        candidate_dir = d + jitter + gravity + light + attract * advanced.attraction_strength * (0.12 + t * 0.18) + avoid * advanced.avoidance_strength * (0.18 + t * 0.30)
        if candidate_dir.length_squared <= 1e-10:
            candidate_dir = d
        candidate_dir.normalize()

        best_dir = candidate_dir
        best_cost = field.collision_cost(pos + best_dir * step, radius, start)
        if best_cost > 0.0:
            u, v = generator._basis(candidate_dir)
            for _ in range(6):
                spread = rng.uniform(0.10, 0.48)
                az = rng.uniform(0.0, math.tau)
                trial = (candidate_dir + (u * math.cos(az) + v * math.sin(az)) * spread + avoid * 0.35).normalized()
                cost = field.collision_cost(pos + trial * step, radius, start)
                if cost < best_cost:
                    best_dir, best_cost = trial, cost
                    if cost <= 0.0:
                        break

        next_pos = pos + best_dir * step
        field.add_segment(pos, next_pos, radius)
        pos = next_pos
        d = best_dir
    return points


def _competition_generate_skeleton(settings):
    global _ACTIVE_FIELD
    advanced = _advanced_settings()
    if not advanced or not advanced.use_space_colonization or _lod_index(settings.lod) > advanced.competition_lod_max:
        return _ORIGINAL_GENERATE(settings)

    _ACTIVE_FIELD = CanopyCompetitionField(settings, advanced)
    try:
        branches, terminals = _ORIGINAL_GENERATE(settings)
        if branches:
            branches[0]["competition_remaining_attractors"] = len(_ACTIVE_FIELD.attractors)
        return branches, terminals
    finally:
        _ACTIVE_FIELD = None


def _capture_point_attributes(mesh):
    captured = {}
    for name in ("trees2_branch_level", "trees2_branch_id", "trees2_wind_weight", "trees2_wind_phase", "trees2_stiffness"):
        attr = mesh.attributes.get(name)
        if not attr or attr.domain != "POINT":
            continue
        captured[name] = (attr.data_type, [item.value for item in attr.data])
    return captured


def _reproject_attributes(mesh, old_positions, captured):
    if not old_positions or not captured:
        return
    tree = KDTree(len(old_positions))
    for index, position in enumerate(old_positions):
        tree.insert(position, index)
    tree.balance()
    nearest = [tree.find(vertex.co)[1] for vertex in mesh.vertices]
    for name, (data_type, values) in captured.items():
        existing = mesh.attributes.get(name)
        if existing:
            mesh.attributes.remove(existing)
        attr = mesh.attributes.new(name=name, type=data_type, domain="POINT")
        for item, source_index in zip(attr.data, nearest):
            item.value = values[source_index]


def _fallback_uv(mesh, settings):
    while mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[0])
    layer = mesh.uv_layers.new(name="UVMap")
    scale = settings.bark_uv_scale
    vertical_scale = max(settings.base_radius * 2.0, 0.02)
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            p = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            u = (math.atan2(p.y, p.x) / math.tau + 0.5) * scale
            v = p.z / vertical_scale * scale
            layer.data[loop_index].uv = (u, v)


def _fused_branch_mesh(collection, branches, settings, bark_material, suffix):
    obj = _ORIGINAL_BRANCH_MESH(collection, branches, settings, bark_material, suffix)
    advanced = _advanced_settings()
    if not advanced or advanced.junction_mode != "VOXEL_FUSE" or _lod_index(settings.lod) > advanced.junction_fuse_lod_max:
        obj["trees2_junction_mode"] = "COLLAR"
        return obj

    mesh = obj.data
    old_positions = [vertex.co.copy() for vertex in mesh.vertices]
    captured = _capture_point_attributes(mesh) if advanced.reproject_branch_attributes else {}
    before_vertices = len(mesh.vertices)
    previous_active = bpy.context.view_layer.objects.active
    previous_selected = list(bpy.context.selected_objects)
    try:
        bpy.ops.object.select_all(action="DESELECT")
        obj.hide_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        mesh.remesh_mode = "VOXEL"
        mesh.remesh_voxel_size = advanced.junction_voxel_size
        mesh.remesh_voxel_adaptivity = advanced.junction_adaptivity
        bpy.ops.object.voxel_remesh()

        mesh = obj.data
        if not mesh.materials:
            mesh.materials.append(bark_material)
        for poly in mesh.polygons:
            poly.use_smooth = True
        if advanced.reproject_branch_attributes:
            _reproject_attributes(mesh, old_positions, captured)
        _fallback_uv(mesh, settings)
        obj["trees2_junction_mode"] = "VOXEL_FUSED"
        obj["trees2_pre_fuse_vertices"] = before_vertices
        obj["trees2_post_fuse_vertices"] = len(mesh.vertices)
        obj["trees2_junction_voxel_size"] = advanced.junction_voxel_size
    except Exception as exc:
        obj["trees2_junction_mode"] = "FUSE_FAILED"
        obj["trees2_junction_error"] = str(exc)
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for selected in previous_selected:
            if selected and selected.name in bpy.data.objects:
                selected.select_set(True)
        if previous_active and previous_active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = previous_active
    return obj


def _box_projected_bark_material(settings, suffix):
    mat = _ORIGINAL_BARK_MATERIAL(settings, suffix)
    advanced = _advanced_settings()
    if not advanced or advanced.junction_mode != "VOXEL_FUSE" or (not settings.bark_image and not settings.bark_normal_image):
        return mat

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    texcoord = nodes.new("ShaderNodeTexCoord")
    texcoord.name = "Trees2 Fused Coordinates"
    mapping = nodes.new("ShaderNodeMapping")
    mapping.name = "Trees2 Bark Box Mapping"
    repeat = max(1.0, settings.bark_uv_scale)
    mapping.inputs["Scale"].default_value = (4.0 * repeat, 4.0 * repeat, 8.0 * repeat)
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    for name in ("Bark Color", "Bark Normal"):
        tex = nodes.get(name)
        if not tex:
            continue
        tex.projection = "BOX"
        tex.projection_blend = 0.22
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    return mat


def install():
    global _ORIGINAL_GENERATE, _ORIGINAL_POLYLINE, _ORIGINAL_BRANCH_MESH, _ORIGINAL_BARK_MATERIAL, _INSTALLED
    if _INSTALLED:
        return
    _ORIGINAL_GENERATE = generator.generate_skeleton
    _ORIGINAL_POLYLINE = generator._branch_polyline
    _ORIGINAL_BRANCH_MESH = generator.create_branch_mesh
    _ORIGINAL_BARK_MATERIAL = generator.create_bark_material
    generator.generate_skeleton = _competition_generate_skeleton
    generator._branch_polyline = _competitive_polyline
    generator.create_branch_mesh = _fused_branch_mesh
    generator.create_bark_material = _box_projected_bark_material
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _ORIGINAL_GENERATE
    generator._branch_polyline = _ORIGINAL_POLYLINE
    generator.create_branch_mesh = _ORIGINAL_BRANCH_MESH
    generator.create_bark_material = _ORIGINAL_BARK_MATERIAL
    _INSTALLED = False
