import json
import math
import random

import bpy
from mathutils import Euler, Vector

from .materials import create_bark_material, create_leaf_material


LOD = {
    "LOD0": dict(branch_factor=1.0, segment_factor=1.0, sides=10, foliage=1.0, max_levels=3),
    "LOD1": dict(branch_factor=0.72, segment_factor=0.78, sides=8, foliage=0.62, max_levels=3),
    "LOD2": dict(branch_factor=0.42, segment_factor=0.58, sides=6, foliage=0.30, max_levels=2),
    "LOD3": dict(branch_factor=0.18, segment_factor=0.38, sides=4, foliage=0.09, max_levels=1),
}


def _safe_name(seed, lod):
    return f"{seed}_{lod}"


def _basis(direction):
    tangent = direction.normalized()
    helper = Vector((0.0, 0.0, 1.0))
    if abs(tangent.dot(helper)) > 0.92:
        helper = Vector((1.0, 0.0, 0.0))
    u = tangent.cross(helper).normalized()
    v = tangent.cross(u).normalized()
    return u, v


def _branch_polyline(rng, start, direction, length, base_radius, segments, bend, droop):
    points = []
    pos = start.copy()
    d = direction.normalized()
    step = length / max(segments, 1)
    for i in range(segments + 1):
        t = i / max(segments, 1)
        radius = max(base_radius * (1.0 - t) ** 1.35, base_radius * 0.045)
        points.append((pos.copy(), radius))
        if i == segments:
            break
        jitter = Vector((
            rng.uniform(-1.0, 1.0),
            rng.uniform(-1.0, 1.0),
            rng.uniform(-0.45, 0.45),
        )) * bend * 0.12
        d = (d + jitter + Vector((0.0, 0.0, -droop * (0.018 + t * 0.07)))).normalized()
        pos += d * step
    return points


def _point_on_polyline(poly, factor):
    factor = min(max(factor, 0.0), 1.0)
    f = factor * (len(poly) - 1)
    i = min(int(f), len(poly) - 2)
    a = f - i
    p0, r0 = poly[i]
    p1, r1 = poly[i + 1]
    return p0.lerp(p1, a), r0 * (1.0 - a) + r1 * a, (p1 - p0).normalized()


def generate_skeleton(settings):
    rng = random.Random(settings.seed)
    cfg = LOD[settings.lod]
    height = settings.height
    trunk_segments = max(4, round(settings.trunk_segments * cfg["segment_factor"]))

    trunk = []
    x = y = 0.0
    phase = rng.uniform(0.0, math.tau)
    for i in range(trunk_segments + 1):
        t = i / trunk_segments
        if i:
            sway = settings.trunk_irregularity * settings.base_radius * 0.32
            x += math.sin(phase + t * 8.0) * sway + rng.uniform(-sway, sway) * 0.25
            y += math.cos(phase * 0.73 + t * 7.0) * sway + rng.uniform(-sway, sway) * 0.25
        z = height * t
        radius = settings.base_radius * max(0.025, (1.0 - t) ** settings.trunk_taper)
        trunk.append((Vector((x, y, z)), radius))

    branches = [trunk]
    terminal = []
    primary_count = max(2, round(settings.primary_branches * cfg["branch_factor"]))
    max_levels = min(settings.branch_levels, cfg["max_levels"])

    def grow_children(parent, level, base_length):
        if level > max_levels:
            terminal.append(parent)
            return

        if level == 1:
            count = primary_count
            factors = [
                settings.branch_start + (0.96 - settings.branch_start) * ((i + 0.35) / count)
                for i in range(count)
            ]
        else:
            count = max(1, round(settings.secondary_per_branch * cfg["branch_factor"]))
            factors = [0.34 + 0.58 * ((i + 0.5) / count) for i in range(count)]

        made = 0
        for idx, f in enumerate(factors):
            if level > 1 and rng.random() > 0.88:
                continue
            start, parent_radius, tangent = _point_on_polyline(parent, f)
            u, v = _basis(tangent)
            az = (idx / max(count, 1)) * math.tau + rng.uniform(-0.5, 0.5)
            radial = (u * math.cos(az) + v * math.sin(az)).normalized()

            if level == 1:
                vertical = Vector((0.0, 0.0, 1.0))
                angle = settings.branch_angle * rng.uniform(0.78, 1.14)
                direction = (vertical * math.cos(angle) + radial * math.sin(angle)).normalized()
                length = base_length * rng.uniform(
                    1.0 - settings.branch_length_randomness,
                    1.0 + settings.branch_length_randomness,
                ) * (0.62 + 0.48 * (1.0 - f))
            else:
                direction = (tangent * rng.uniform(0.30, 0.62) + radial * rng.uniform(0.72, 1.0) + Vector((0, 0, 0.12))).normalized()
                length = base_length * (0.46 ** (level - 1)) * rng.uniform(0.72, 1.15)

            branch_radius = max(parent_radius * (0.58 if level == 1 else 0.46), settings.base_radius * 0.012)
            segs = max(3, round((7 - level) * cfg["segment_factor"]))
            child = _branch_polyline(
                rng, start, direction, length, branch_radius, segs,
                settings.branch_bend * (1.0 + 0.18 * level),
                settings.branch_droop * (1.0 + 0.22 * level),
            )
            branches.append(child)
            made += 1
            grow_children(child, level + 1, base_length)

        if made == 0:
            terminal.append(parent)

    grow_children(trunk, 1, settings.branch_length)
    if not terminal:
        terminal = branches[1:] or [trunk]
    return branches, terminal


def create_branch_mesh(collection, branches, settings, bark_material, suffix):
    cfg = LOD[settings.lod]
    verts = []
    faces = []

    for poly in branches:
        if len(poly) < 2:
            continue
        ring_starts = []
        for i, (p, radius) in enumerate(poly):
            if i == 0:
                tangent = poly[1][0] - p
            elif i == len(poly) - 1:
                tangent = p - poly[i - 1][0]
            else:
                tangent = poly[i + 1][0] - poly[i - 1][0]
            sides = max(3, min(cfg["sides"], round(3 + radius / max(settings.base_radius, 1e-5) * (cfg["sides"] - 3))))
            u, v = _basis(tangent)
            start = len(verts)
            ring_starts.append((start, sides))
            for s in range(sides):
                a = math.tau * s / sides
                verts.append(p + (u * math.cos(a) + v * math.sin(a)) * radius)

        for i in range(len(ring_starts) - 1):
            a_start, a_sides = ring_starts[i]
            b_start, b_sides = ring_starts[i + 1]
            steps = max(a_sides, b_sides)
            for s in range(steps):
                a0 = a_start + int(s * a_sides / steps) % a_sides
                a1 = a_start + int((s + 1) * a_sides / steps) % a_sides
                b1 = b_start + int((s + 1) * b_sides / steps) % b_sides
                b0 = b_start + int(s * b_sides / steps) % b_sides
                if len({a0, a1, b1, b0}) >= 3:
                    faces.append((a0, a1, b1, b0))

    mesh = bpy.data.meshes.new(f"Trees2_Branches_{suffix}")
    mesh.from_pydata([v[:] for v in verts], [], faces)
    mesh.materials.append(bark_material)
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(f"Trees2_Branches_{suffix}", mesh)
    collection.objects.link(obj)
    return obj


def _leaf_transform(rng, position, settings):
    yaw = rng.uniform(0.0, math.tau)
    pitch = rng.uniform(-0.85, 0.85)
    roll = rng.uniform(-0.55, 0.55)
    q = Euler((pitch, roll, yaw), "XYZ").to_quaternion()
    s = settings.card_scale * rng.uniform(
        1.0 - settings.card_scale_randomness,
        1.0 + settings.card_scale_randomness,
    )
    return position, q, Vector((s, s, s))


def generate_foliage_points(settings, terminals):
    rng = random.Random(settings.seed ^ 0x5F3759DF)
    cfg = LOD[settings.lod]
    points, rotations, scales = [], [], []

    for poly in terminals:
        if len(poly) < 2:
            continue
        length = sum((poly[i + 1][0] - poly[i][0]).length for i in range(len(poly) - 1))
        count = max(1, round(length * 3.2 * settings.foliage_density * cfg["foliage"]))
        for _ in range(count):
            f = rng.uniform(settings.foliage_start, 1.0)
            p, _, tangent = _point_on_polyline(poly, f)
            u, v = _basis(tangent)
            envelope = settings.card_scale * rng.uniform(0.15, 0.70)
            p = p + u * rng.uniform(-envelope, envelope) + v * rng.uniform(-envelope, envelope)
            pos, q, scale = _leaf_transform(rng, p, settings)
            points.append(pos)
            rotations.append(q)
            scales.append(scale)
    return points, rotations, scales


def create_leaf_source(collection, settings, leaf_material, suffix):
    verts, faces, uvs = [], [], []
    planes = {"SINGLE": 1, "CROSS": 2, "TRI": 3}[settings.card_style]
    h = settings.card_aspect
    for i in range(planes):
        angle = math.pi * i / planes
        normal = Vector((math.cos(angle), math.sin(angle), 0.0))
        horizontal = Vector((-normal.y, normal.x, 0.0))
        base = len(verts)
        verts.extend([
            horizontal * -0.5 + Vector((0, 0, -0.5 * h)),
            horizontal * 0.5 + Vector((0, 0, -0.5 * h)),
            horizontal * 0.5 + Vector((0, 0, 0.5 * h)),
            horizontal * -0.5 + Vector((0, 0, 0.5 * h)),
        ])
        faces.append((base, base + 1, base + 2, base + 3))
        uvs.extend(((0, 0), (1, 0), (1, 1), (0, 1)))

    mesh = bpy.data.meshes.new(f"Trees2_LeafCard_{suffix}")
    mesh.from_pydata([v[:] for v in verts], [], faces)
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            uv_layer.data[li].uv = uvs[vi]
    mesh.materials.append(leaf_material)
    obj = bpy.data.objects.new(f"Trees2_LeafCard_{suffix}", mesh)
    collection.objects.link(obj)
    obj.hide_render = True
    obj.hide_set(True)
    obj["trees2_internal"] = True
    return obj


def create_leaf_points(collection, points, rotations, scales, source_obj, settings, suffix):
    mesh = bpy.data.meshes.new(f"Trees2_FoliagePoints_{suffix}")
    mesh.from_pydata([p[:] for p in points], [], [])

    rot_attr = mesh.attributes.new(name="trees2_rotation", type="QUATERNION", domain="POINT")
    scale_attr = mesh.attributes.new(name="trees2_scale", type="FLOAT_VECTOR", domain="POINT")
    for i, (q, s) in enumerate(zip(rotations, scales)):
        rot_attr.data[i].value = (q.w, q.x, q.y, q.z)
        scale_attr.data[i].vector = s

    obj = bpy.data.objects.new(f"Trees2_Foliage_{suffix}", mesh)
    collection.objects.link(obj)
    obj["trees2_foliage"] = True

    group = bpy.data.node_groups.new(f"Trees2_InstanceLeaves_{suffix}", "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes = group.nodes
    links = group.links

    inp = nodes.new("NodeGroupInput")
    out = nodes.new("NodeGroupOutput")
    inp.location = (-620, 80)
    out.location = (420, 80)

    obj_info = nodes.new("GeometryNodeObjectInfo")
    obj_info.location = (-620, -160)
    obj_info.transform_space = "ORIGINAL"
    obj_info.inputs["Object"].default_value = source_obj

    rot = nodes.new("GeometryNodeInputNamedAttribute")
    rot.data_type = "QUATERNION"
    rot.location = (-390, -250)
    rot.inputs["Name"].default_value = "trees2_rotation"

    scale = nodes.new("GeometryNodeInputNamedAttribute")
    scale.data_type = "FLOAT_VECTOR"
    scale.location = (-390, -390)
    scale.inputs["Name"].default_value = "trees2_scale"

    inst = nodes.new("GeometryNodeInstanceOnPoints")
    inst.location = (-80, 80)
    links.new(inp.outputs["Geometry"], inst.inputs["Points"])
    links.new(obj_info.outputs["Geometry"], inst.inputs["Instance"])
    links.new(rot.outputs["Attribute"], inst.inputs["Rotation"])
    links.new(scale.outputs["Attribute"], inst.inputs["Scale"])

    if settings.realize_foliage:
        realize = nodes.new("GeometryNodeRealizeInstances")
        realize.location = (180, 80)
        links.new(inst.outputs["Instances"], realize.inputs["Geometry"])
        links.new(realize.outputs["Geometry"], out.inputs["Geometry"])
    else:
        links.new(inst.outputs["Instances"], out.inputs["Geometry"])

    mod = obj.modifiers.new(name="Trees2 Instanced Foliage", type="NODES")
    mod.node_group = group
    return obj


def _settings_snapshot(settings):
    keys = (
        "seed", "height", "base_radius", "trunk_segments", "trunk_irregularity", "trunk_taper",
        "branch_levels", "primary_branches", "secondary_per_branch", "branch_start", "branch_angle",
        "branch_length", "branch_length_randomness", "branch_bend", "branch_droop", "foliage_density",
        "foliage_start", "card_scale", "card_scale_randomness", "card_aspect", "card_style", "lod",
        "realize_foliage",
    )
    return {key: getattr(settings, key) for key in keys}


def build_tree(context, settings, location=None):
    suffix = _safe_name(settings.seed, settings.lod)
    root = bpy.data.collections.new(f"Trees2_Tree_{suffix}")
    context.scene.collection.children.link(root)
    root["trees2_tree"] = True
    root["trees2_settings"] = json.dumps(_settings_snapshot(settings))

    internal = bpy.data.collections.new(f"Trees2_Internal_{suffix}")
    root.children.link(internal)
    internal.hide_render = True
    internal.hide_viewport = False

    bark = create_bark_material(settings, suffix)
    leaves = create_leaf_material(settings, suffix)
    branches, terminal = generate_skeleton(settings)
    branch_obj = create_branch_mesh(root, branches, settings, bark, suffix)
    points, rotations, scales = generate_foliage_points(settings, terminal)
    leaf_source = create_leaf_source(internal, settings, leaves, suffix)
    leaf_obj = create_leaf_points(root, points, rotations, scales, leaf_source, settings, suffix)

    loc = Vector(location) if location is not None else context.scene.cursor.location.copy()
    branch_obj.location = loc
    leaf_obj.location = loc
    leaf_source.location = loc

    branch_obj["trees2_root_collection"] = root.name
    leaf_obj["trees2_root_collection"] = root.name
    branch_obj["trees2_leaf_points"] = len(points)
    branch_obj["trees2_branch_count"] = len(branches)

    for obj in context.selected_objects:
        obj.select_set(False)
    branch_obj.select_set(True)
    context.view_layer.objects.active = branch_obj
    return root, branch_obj, leaf_obj


def remove_tree_collection(root):
    objects = []

    def collect(col):
        objects.extend(list(col.objects))
        for child in list(col.children):
            collect(child)

    collect(root)
    for obj in objects:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and getattr(data, "users", 0) == 0 and isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
    for child in list(root.children):
        bpy.data.collections.remove(child)
    bpy.data.collections.remove(root)
