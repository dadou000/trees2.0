import json
import math
import random

import bpy
from mathutils import Euler, Vector

from .materials import create_bark_material, create_leaf_material


GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))

LOD = {
    "LOD0": dict(branch_factor=1.00, segment_factor=1.00, sides=10, foliage=1.00, max_levels=4, card_scale=1.00),
    "LOD1": dict(branch_factor=0.76, segment_factor=0.82, sides=8, foliage=0.66, max_levels=3, card_scale=1.05),
    "LOD2": dict(branch_factor=0.48, segment_factor=0.62, sides=6, foliage=0.34, max_levels=2, card_scale=1.18),
    "LOD3": dict(branch_factor=0.22, segment_factor=0.42, sides=4, foliage=0.12, max_levels=1, card_scale=1.55),
    "LOD4": dict(branch_factor=0.09, segment_factor=0.28, sides=3, foliage=0.035, max_levels=1, card_scale=2.80),
}


def _clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def _safe_name(seed, lod):
    return f"{seed}_{lod}_{len(bpy.data.collections):04d}"


def _basis(direction):
    tangent = direction.normalized()
    helper = Vector((0.0, 0.0, 1.0))
    if abs(tangent.dot(helper)) > 0.92:
        helper = Vector((1.0, 0.0, 0.0))
    u = tangent.cross(helper).normalized()
    v = tangent.cross(u).normalized()
    return u, v


def _crown_profile(shape, factor, start):
    x = _clamp((factor - start) / max(1.0 - start, 1e-5))
    if shape == "CONICAL":
        return 0.12 + 0.95 * (1.0 - x) ** 0.62
    if shape == "COLUMNAR":
        return 0.68 + 0.22 * math.sin(math.pi * x) ** 0.7
    if shape == "VASE":
        return 0.28 + 0.82 * x ** 0.58
    if shape == "UMBRELLA":
        dome = math.exp(-((x - 0.73) / 0.27) ** 2)
        return 0.20 + 0.95 * dome
    if shape == "OVAL":
        return 0.18 + 0.88 * math.sin(math.pi * x) ** 0.82
    return 0.18 + 0.92 * math.sin(math.pi * x) ** 0.58


def _branch_azimuth(settings, rng, index, count, level):
    if settings.branch_distribution == "RANDOM":
        return rng.uniform(0.0, math.tau)
    if settings.branch_distribution == "WHORLED":
        whorl_size = 3
        whorl = index // whorl_size
        slot = index % whorl_size
        return whorl * GOLDEN_ANGLE * 0.72 + slot * math.tau / whorl_size + rng.uniform(-settings.azimuth_jitter, settings.azimuth_jitter)
    return index * GOLDEN_ANGLE + level * 0.31 + rng.uniform(-settings.azimuth_jitter, settings.azimuth_jitter)


def _branch_polyline(rng, start, direction, length, base_radius, segments, bend, droop, upward, collar=0.0):
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

        jitter = Vector((
            rng.uniform(-1.0, 1.0),
            rng.uniform(-1.0, 1.0),
            rng.uniform(-0.50, 0.50),
        )) * bend * (0.085 + t * 0.035)
        gravity = Vector((0.0, 0.0, -droop * (0.010 + t * 0.055)))
        light = Vector((0.0, 0.0, upward * (0.008 + t * 0.018)))
        d = (d + jitter + gravity + light).normalized()
        pos += d * step
    return points


def _point_on_polyline(poly, factor):
    points = poly["points"] if isinstance(poly, dict) else poly
    factor = _clamp(factor)
    f = factor * (len(points) - 1)
    i = min(int(f), len(points) - 2)
    a = f - i
    p0, r0 = points[i]
    p1, r1 = points[i + 1]
    return p0.lerp(p1, a), r0 * (1.0 - a) + r1 * a, (p1 - p0).normalized()


def _polyline_length(branch):
    points = branch["points"]
    return sum((points[i + 1][0] - points[i][0]).length for i in range(len(points) - 1))


def generate_skeleton(settings):
    rng = random.Random(settings.seed)
    cfg = LOD[settings.lod]
    height = settings.height
    trunk_segments = max(4, round(settings.trunk_segments * cfg["segment_factor"]))

    trunk_points = []
    x = y = 0.0
    phase = rng.uniform(0.0, math.tau)
    for i in range(trunk_segments + 1):
        t = i / trunk_segments
        if i:
            sway = settings.trunk_irregularity * settings.base_radius * 0.30
            x += math.sin(phase + t * 7.8) * sway + rng.uniform(-sway, sway) * 0.22
            y += math.cos(phase * 0.71 + t * 6.9) * sway + rng.uniform(-sway, sway) * 0.22
        z = height * t
        radius = settings.base_radius * max(0.025, (1.0 - t) ** settings.trunk_taper)
        if t < 0.13:
            flare = (1.0 - t / 0.13) ** 2
            radius *= 1.0 + settings.root_flare * flare
        trunk_points.append((Vector((x, y, z)), radius))

    next_id = 1
    trunk = {
        "id": 0, "level": 0, "parent_id": -1, "points": trunk_points,
        "dead": False, "phase": rng.random(), "length": height,
    }
    branches = [trunk]
    terminals = []
    primary_count = max(2, round(settings.primary_branches * cfg["branch_factor"]))
    max_levels = min(settings.branch_levels, cfg["max_levels"])

    def grow_children(parent, level):
        nonlocal next_id
        if level > max_levels or parent["dead"]:
            if parent["level"] > 0 and not parent["dead"]:
                terminals.append(parent)
            return

        if level == 1:
            count = primary_count
            factors = [
                settings.branch_start + (0.965 - settings.branch_start) * ((i + 0.35) / max(count, 1))
                for i in range(count)
            ]
        else:
            count = max(1, round(settings.secondary_per_branch * cfg["branch_factor"] * (0.92 ** (level - 2))))
            factors = [0.30 + 0.64 * ((i + 0.5) / max(count, 1)) for i in range(count)]

        made = 0
        for idx, f in enumerate(factors):
            prune = settings.prune_probability * (1.25 if level > 1 else 0.65)
            if rng.random() < prune:
                continue

            start, parent_radius, tangent = _point_on_polyline(parent, f)
            u, v = _basis(tangent)
            az = _branch_azimuth(settings, rng, idx + parent["id"] * 3, count, level)
            radial = (u * math.cos(az) + v * math.sin(az)).normalized()

            if level == 1:
                angle = settings.branch_angle * rng.uniform(0.82, 1.13)
                direction = (tangent * math.cos(angle) + radial * math.sin(angle)).normalized()
                direction = (direction + Vector((0.0, 0.0, settings.phototropism * 0.12))).normalized()
                crown = _crown_profile(settings.crown_shape, f, settings.branch_start)
                crown_x = _clamp((f - settings.branch_start) / max(1.0 - settings.branch_start, 1e-5))
                dominance = 1.0 - settings.apical_dominance * crown_x * 0.56
                length = settings.branch_length * crown * dominance
                length *= rng.uniform(1.0 - settings.branch_length_randomness, 1.0 + settings.branch_length_randomness)
                radius_ratio = rng.uniform(0.46, 0.60)
            else:
                outward = rng.uniform(0.66, 0.96)
                forward = rng.uniform(0.30, 0.60)
                direction = (tangent * forward + radial * outward + Vector((0.0, 0.0, settings.phototropism * 0.16))).normalized()
                length = parent["length"] * rng.uniform(0.40, 0.57)
                length *= 1.0 - settings.apical_dominance * 0.10 * level
                radius_ratio = rng.uniform(0.38, 0.49)

            if length <= settings.base_radius * 0.16:
                continue

            branch_radius = max(parent_radius * radius_ratio, settings.base_radius * 0.009)
            segs = max(2, round((8 - level) * cfg["segment_factor"] + length * 0.15))
            dead_chance = settings.dead_branch_probability * (0.45 + level * 0.32)
            dead = rng.random() < dead_chance
            child_points = _branch_polyline(
                rng, start, direction, length, branch_radius, segs,
                settings.branch_bend * (1.0 + 0.16 * level),
                settings.branch_droop * (1.0 + 0.24 * level),
                settings.phototropism,
                settings.branch_collar,
            )
            child = {
                "id": next_id, "level": level, "parent_id": parent["id"], "points": child_points,
                "dead": dead, "phase": rng.random(), "length": length,
            }
            next_id += 1
            branches.append(child)
            made += 1
            if dead:
                continue
            grow_children(child, level + 1)

        if made == 0 and parent["level"] > 0 and not parent["dead"]:
            terminals.append(parent)

    grow_children(trunk, 1)
    if not terminals:
        terminals = [b for b in branches if b["level"] > 0 and not b["dead"]] or [trunk]
    return branches, terminals


def _append_mesh_attribute(mesh, name, data_type, values):
    attr = mesh.attributes.new(name=name, type=data_type, domain="POINT")
    if data_type == "FLOAT_VECTOR":
        for item, value in zip(attr.data, values):
            item.vector = value
    else:
        for item, value in zip(attr.data, values):
            item.value = value
    return attr


def create_branch_mesh(collection, branches, settings, bark_material, suffix):
    cfg = LOD[settings.lod]
    verts = []
    faces = []
    face_uvs = []
    branch_levels = []
    branch_ids = []
    wind_weights = []
    wind_phases = []
    stiffnesses = []

    max_level = max(1, settings.branch_levels)

    for branch in branches:
        points = branch["points"]
        if len(points) < 2:
            continue
        ring_starts = []
        cumulative = [0.0]
        for i in range(1, len(points)):
            cumulative.append(cumulative[-1] + (points[i][0] - points[i - 1][0]).length)

        for i, (p, radius) in enumerate(points):
            if i == 0:
                tangent = points[1][0] - p
            elif i == len(points) - 1:
                tangent = p - points[i - 1][0]
            else:
                tangent = points[i + 1][0] - points[i - 1][0]
            sides = max(3, min(cfg["sides"], round(3 + radius / max(settings.base_radius, 1e-5) * (cfg["sides"] - 3))))
            u, v = _basis(tangent)
            start = len(verts)
            ring_starts.append((start, sides, cumulative[i]))

            h = _clamp(p.z / max(settings.height, 1e-5))
            level_factor = branch["level"] / max_level
            wind = (h ** settings.wind_height_power) * (0.18 + 0.82 * level_factor)
            stiffness = _clamp(1.0 - wind * 0.88)
            for s in range(sides):
                a = math.tau * s / sides
                verts.append(p + (u * math.cos(a) + v * math.sin(a)) * radius)
                branch_levels.append(branch["level"])
                branch_ids.append(branch["id"])
                wind_weights.append(wind)
                wind_phases.append(branch["phase"])
                stiffnesses.append(stiffness)

        for i in range(len(ring_starts) - 1):
            a_start, a_sides, a_len = ring_starts[i]
            b_start, b_sides, b_len = ring_starts[i + 1]
            steps = max(a_sides, b_sides)
            v0 = a_len / max(settings.base_radius * 2.0, 0.01) * settings.bark_uv_scale
            v1 = b_len / max(settings.base_radius * 2.0, 0.01) * settings.bark_uv_scale
            for s in range(steps):
                a0 = a_start + int(s * a_sides / steps) % a_sides
                a1 = a_start + int((s + 1) * a_sides / steps) % a_sides
                b1 = b_start + int((s + 1) * b_sides / steps) % b_sides
                b0 = b_start + int(s * b_sides / steps) % b_sides
                face = (a0, a1, b1, b0)
                if len(set(face)) >= 3:
                    faces.append(face)
                    u0 = s / steps
                    u1 = (s + 1) / steps
                    face_uvs.append(((u0, v0), (u1, v0), (u1, v1), (u0, v1)))

        if settings.cap_branch_tips:
            end_start, end_sides, _ = ring_starts[-1]
            center_index = len(verts)
            p = points[-1][0]
            verts.append(p.copy())
            branch_levels.append(branch["level"])
            branch_ids.append(branch["id"])
            h = _clamp(p.z / max(settings.height, 1e-5))
            level_factor = branch["level"] / max_level
            wind = (h ** settings.wind_height_power) * (0.18 + 0.82 * level_factor)
            wind_weights.append(wind)
            wind_phases.append(branch["phase"])
            stiffnesses.append(_clamp(1.0 - wind * 0.88))
            for s in range(end_sides):
                n0 = end_start + s
                n1 = end_start + (s + 1) % end_sides
                faces.append((center_index, n1, n0))
                face_uvs.append(((0.5, 0.5), (0.5 + 0.5 * math.cos(math.tau * (s + 1) / end_sides), 0.5 + 0.5 * math.sin(math.tau * (s + 1) / end_sides)), (0.5 + 0.5 * math.cos(math.tau * s / end_sides), 0.5 + 0.5 * math.sin(math.tau * s / end_sides))))

    mesh = bpy.data.meshes.new(f"Trees2_Branches_{suffix}")
    mesh.from_pydata([v[:] for v in verts], [], faces)
    mesh.materials.append(bark_material)
    for poly in mesh.polygons:
        poly.use_smooth = True

    uv_layer = mesh.uv_layers.new(name="UVMap")
    for poly, coords in zip(mesh.polygons, face_uvs):
        for loop_index, uv in zip(poly.loop_indices, coords):
            uv_layer.data[loop_index].uv = uv

    _append_mesh_attribute(mesh, "trees2_branch_level", "INT", branch_levels)
    _append_mesh_attribute(mesh, "trees2_branch_id", "INT", branch_ids)
    if settings.generate_wind_attributes:
        _append_mesh_attribute(mesh, "trees2_wind_weight", "FLOAT", wind_weights)
        _append_mesh_attribute(mesh, "trees2_wind_phase", "FLOAT", wind_phases)
        _append_mesh_attribute(mesh, "trees2_stiffness", "FLOAT", stiffnesses)

    obj = bpy.data.objects.new(f"Trees2_Branches_{suffix}", mesh)
    collection.objects.link(obj)
    return obj


def _leaf_transform(rng, settings, cfg):
    yaw = rng.uniform(0.0, math.tau)
    tilt = (1.0 - settings.leaf_up_bias) * 1.15 + 0.10
    pitch = rng.uniform(-tilt, tilt)
    roll = rng.uniform(-tilt * 0.72, tilt * 0.72)
    q = Euler((pitch, roll, yaw), "XYZ").to_quaternion()
    scale = settings.card_scale * cfg["card_scale"] * rng.uniform(
        1.0 - settings.card_scale_randomness,
        1.0 + settings.card_scale_randomness,
    )
    return q, Vector((scale, scale, scale))


def generate_foliage_points(settings, terminals):
    rng = random.Random(settings.seed ^ 0x5F3759DF)
    cfg = LOD[settings.lod]
    atlas_count = max(1, min(settings.atlas_variants, settings.atlas_columns * settings.atlas_rows))
    records = []

    for branch in terminals:
        if branch["dead"] or len(branch["points"]) < 2:
            continue
        length = _polyline_length(branch)
        count = max(1, round(length * 3.1 * settings.foliage_density * cfg["foliage"]))
        for _ in range(count):
            r = rng.random()
            biased = 1.0 - (1.0 - r) ** (1.0 + settings.foliage_tip_bias * 3.2)
            f = settings.foliage_start + (1.0 - settings.foliage_start) * biased
            p, _, tangent = _point_on_polyline(branch, f)
            u, v = _basis(tangent)
            envelope = settings.card_scale * settings.foliage_spread * cfg["card_scale"] * rng.uniform(0.18, 0.72)
            p = p + u * rng.uniform(-envelope, envelope) + v * rng.uniform(-envelope, envelope)
            q, scale = _leaf_transform(rng, settings, cfg)
            h = _clamp(p.z / max(settings.height, 1e-5))
            wind = h ** settings.wind_height_power
            records.append({
                "position": p,
                "rotation": q,
                "scale": scale,
                "atlas": rng.randrange(atlas_count),
                "wind": wind,
                "phase": (branch["phase"] + rng.uniform(-0.18, 0.18)) % 1.0,
                "stiffness": _clamp(0.42 - wind * 0.32),
            })
    return records


def _atlas_uv(index, columns, rows):
    columns = max(1, columns)
    rows = max(1, rows)
    col = index % columns
    row = index // columns
    u0 = col / columns
    u1 = (col + 1) / columns
    v1 = 1.0 - row / rows
    v0 = 1.0 - (row + 1) / rows
    return u0, v0, u1, v1


def _create_leaf_card_mesh(settings, leaf_material, suffix, index):
    verts = []
    faces = []
    face_uvs = []
    planes = {"SINGLE": 1, "CROSS": 2, "TRI": 3}[settings.card_style]
    aspect = settings.card_aspect
    u0, v0, u1, v1 = _atlas_uv(index, settings.atlas_columns, settings.atlas_rows)

    for plane in range(planes):
        angle = math.pi * plane / planes
        normal = Vector((math.cos(angle), math.sin(angle), 0.0))
        horizontal = Vector((-normal.y, normal.x, 0.0))
        columns = (-0.5, 0.0, 0.5)
        ring = []
        for ci, x in enumerate(columns):
            bend = settings.card_bend if ci == 1 else 0.0
            center = horizontal * x + normal * bend
            bottom = center + Vector((0.0, 0.0, -0.5 * aspect))
            top = center + Vector((0.0, 0.0, 0.5 * aspect))
            ring.append((len(verts), len(verts) + 1))
            verts.extend((bottom, top))

        for ci in range(2):
            b0, t0 = ring[ci]
            b1, t1 = ring[ci + 1]
            faces.append((b0, b1, t1, t0))
            fu0 = u0 + (u1 - u0) * (ci / 2.0)
            fu1 = u0 + (u1 - u0) * ((ci + 1) / 2.0)
            face_uvs.append(((fu0, v0), (fu1, v0), (fu1, v1), (fu0, v1)))

    mesh = bpy.data.meshes.new(f"Trees2_LeafCard_{suffix}_{index:03d}")
    mesh.from_pydata([v[:] for v in verts], [], faces)
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for poly, coords in zip(mesh.polygons, face_uvs):
        for loop_index, uv in zip(poly.loop_indices, coords):
            uv_layer.data[loop_index].uv = uv
    mesh.materials.append(leaf_material)
    return mesh


def create_leaf_sources(source_collection, settings, leaf_material, suffix):
    count = max(1, min(settings.atlas_variants, settings.atlas_columns * settings.atlas_rows))
    objects = []
    for index in range(count):
        mesh = _create_leaf_card_mesh(settings, leaf_material, suffix, index)
        obj = bpy.data.objects.new(f"Trees2_Card_{index:03d}_{suffix}", mesh)
        source_collection.objects.link(obj)
        obj.hide_render = True
        obj.hide_set(True)
        obj["trees2_internal"] = True
        obj["trees2_atlas_index"] = index
        objects.append(obj)
    return objects


def create_leaf_points(collection, records, source_collection, settings, suffix):
    positions = [r["position"] for r in records]
    mesh = bpy.data.meshes.new(f"Trees2_FoliagePoints_{suffix}")
    mesh.from_pydata([p[:] for p in positions], [], [])

    rotation = mesh.attributes.new(name="trees2_rotation", type="QUATERNION", domain="POINT")
    scale = mesh.attributes.new(name="trees2_scale", type="FLOAT_VECTOR", domain="POINT")
    atlas = mesh.attributes.new(name="trees2_atlas_index", type="INT", domain="POINT")
    for i, record in enumerate(records):
        q = record["rotation"]
        rotation.data[i].value = (q.w, q.x, q.y, q.z)
        scale.data[i].vector = record["scale"]
        atlas.data[i].value = record["atlas"]

    if settings.generate_wind_attributes:
        wind = mesh.attributes.new(name="trees2_wind_weight", type="FLOAT", domain="POINT")
        phase = mesh.attributes.new(name="trees2_wind_phase", type="FLOAT", domain="POINT")
        stiffness = mesh.attributes.new(name="trees2_stiffness", type="FLOAT", domain="POINT")
        for i, record in enumerate(records):
            wind.data[i].value = record["wind"]
            phase.data[i].value = record["phase"]
            stiffness.data[i].value = record["stiffness"]

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
    inp.location = (-720, 80)
    out.location = (450, 80)

    coll = nodes.new("GeometryNodeCollectionInfo")
    coll.location = (-700, -150)
    coll.transform_space = "RELATIVE"
    coll.inputs["Collection"].default_value = source_collection
    if "Separate Children" in coll.inputs:
        coll.inputs["Separate Children"].default_value = True
    if "Reset Children" in coll.inputs:
        coll.inputs["Reset Children"].default_value = True

    rot = nodes.new("GeometryNodeInputNamedAttribute")
    rot.data_type = "QUATERNION"
    rot.location = (-430, -280)
    rot.inputs["Name"].default_value = "trees2_rotation"

    scale = nodes.new("GeometryNodeInputNamedAttribute")
    scale.data_type = "FLOAT_VECTOR"
    scale.location = (-430, -410)
    scale.inputs["Name"].default_value = "trees2_scale"

    atlas = nodes.new("GeometryNodeInputNamedAttribute")
    atlas.data_type = "INT"
    atlas.location = (-430, -540)
    atlas.inputs["Name"].default_value = "trees2_atlas_index"

    inst = nodes.new("GeometryNodeInstanceOnPoints")
    inst.location = (-80, 80)
    if "Pick Instance" in inst.inputs:
        inst.inputs["Pick Instance"].default_value = True
    links.new(inp.outputs["Geometry"], inst.inputs["Points"])
    links.new(coll.outputs["Instances"], inst.inputs["Instance"])
    links.new(rot.outputs["Attribute"], inst.inputs["Rotation"])
    links.new(scale.outputs["Attribute"], inst.inputs["Scale"])
    links.new(atlas.outputs["Attribute"], inst.inputs["Instance Index"])

    if settings.realize_foliage:
        realize = nodes.new("GeometryNodeRealizeInstances")
        realize.location = (190, 80)
        links.new(inst.outputs["Instances"], realize.inputs["Geometry"])
        links.new(realize.outputs["Geometry"], out.inputs["Geometry"])
    else:
        links.new(inst.outputs["Instances"], out.inputs["Geometry"])

    mod = obj.modifiers.new(name="Trees2 Instanced Foliage", type="NODES")
    mod.node_group = group
    return obj


def _settings_snapshot(settings):
    keys = (
        "seed", "species_preset", "height", "base_radius", "trunk_segments", "trunk_irregularity", "trunk_taper", "root_flare",
        "crown_shape", "branch_distribution", "branch_levels", "primary_branches", "secondary_per_branch", "branch_start",
        "branch_angle", "azimuth_jitter", "branch_length", "branch_length_randomness", "branch_bend", "branch_droop",
        "apical_dominance", "phototropism", "branch_collar", "dead_branch_probability", "prune_probability",
        "foliage_density", "foliage_start", "foliage_tip_bias", "foliage_spread", "leaf_up_bias", "card_scale",
        "card_scale_randomness", "card_aspect", "card_bend", "card_style", "atlas_columns", "atlas_rows", "atlas_variants",
        "bark_uv_scale", "generate_wind_attributes", "wind_height_power", "lod", "realize_foliage", "cap_branch_tips",
    )
    return {key: getattr(settings, key) for key in keys}


def build_tree(context, settings, location=None):
    suffix = _safe_name(settings.seed, settings.lod)
    root = bpy.data.collections.new(f"Trees2_Tree_{suffix}")
    context.scene.collection.children.link(root)
    sources = bpy.data.collections.new(f"Trees2_Sources_{suffix}")
    root.children.link(sources)
    sources["trees2_internal"] = True

    bark_material = create_bark_material(settings, suffix)
    leaf_material = create_leaf_material(settings, suffix)
    branches, terminals = generate_skeleton(settings)
    branch_obj = create_branch_mesh(root, branches, settings, bark_material, suffix)
    records = generate_foliage_points(settings, terminals)
    create_leaf_sources(sources, settings, leaf_material, suffix)
    foliage_obj = create_leaf_points(root, records, sources, settings, suffix)

    tree_location = Vector(location) if location is not None else context.scene.cursor.location.copy()
    branch_obj.location = tree_location
    foliage_obj.location = tree_location

    root["trees2_tree"] = True
    root["trees2_suffix"] = suffix
    root["trees2_seed"] = settings.seed
    root["trees2_lod"] = settings.lod
    root["trees2_settings"] = json.dumps(_settings_snapshot(settings))

    for obj in (branch_obj, foliage_obj):
        obj["trees2_root_collection"] = root.name
        obj["trees2_suffix"] = suffix
    branch_obj["trees2_branch_count"] = len(branches)
    branch_obj["trees2_terminal_count"] = len(terminals)
    branch_obj["trees2_leaf_points"] = len(records)
    branch_obj["trees2_dead_branches"] = sum(1 for b in branches if b["dead"])
    branch_obj["trees2_triangle_estimate"] = sum(len(p.vertices) - 2 for p in branch_obj.data.polygons)

    bpy.ops.object.select_all(action="DESELECT")
    branch_obj.hide_set(False)
    branch_obj.select_set(True)
    context.view_layer.objects.active = branch_obj
    return root, branch_obj, foliage_obj


def _remove_collection_recursive(collection):
    for child in list(collection.children):
        _remove_collection_recursive(child)
    for obj in list(collection.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and getattr(data, "users", 1) == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
    bpy.data.collections.remove(collection)


def remove_tree_collection(root):
    if not root:
        return
    suffix = root.get("trees2_suffix", "")
    _remove_collection_recursive(root)

    if suffix:
        for group in list(bpy.data.node_groups):
            if group.name.startswith("Trees2_InstanceLeaves_") and suffix in group.name and group.users == 0:
                bpy.data.node_groups.remove(group)
        for mat in list(bpy.data.materials):
            if mat.name.startswith("Trees2_") and suffix in mat.name and mat.users == 0:
                bpy.data.materials.remove(mat)
