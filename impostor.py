import json
import math
import os
import tempfile

import bpy
from mathutils import Vector


def _atlas_uv(index, columns, rows):
    col = index % columns
    row = index // columns
    u0 = col / columns
    u1 = (col + 1) / columns
    v1 = 1.0 - row / rows
    v0 = 1.0 - (row + 1) / rows
    return u0, v0, u1, v1


def _tree_objects(root):
    return [obj for obj in root.all_objects if not obj.get("trees2_internal") and not obj.get("trees2_impostor")]


def _tree_bounds(root, context):
    depsgraph = context.evaluated_depsgraph_get()
    minimum = Vector((float("inf"), float("inf"), float("inf")))
    maximum = Vector((float("-inf"), float("-inf"), float("-inf")))
    found = False
    for obj in _tree_objects(root):
        try:
            evaluated = obj.evaluated_get(depsgraph)
            matrix = evaluated.matrix_world
            corners = evaluated.bound_box
        except Exception:
            matrix = obj.matrix_world
            corners = obj.bound_box
        for corner in corners:
            p = matrix @ Vector(corner)
            minimum.x = min(minimum.x, p.x)
            minimum.y = min(minimum.y, p.y)
            minimum.z = min(minimum.z, p.z)
            maximum.x = max(maximum.x, p.x)
            maximum.y = max(maximum.y, p.y)
            maximum.z = max(maximum.z, p.z)
            found = True
    if not found:
        minimum = Vector((-1.0, -1.0, 0.0))
        maximum = Vector((1.0, 1.0, 2.0))
    return minimum, maximum


def _look_at(obj, target):
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _make_render_rig(scene, center, extent):
    camera_data = bpy.data.cameras.new("Trees2_ImpostorCamera")
    camera_data.type = "ORTHO"
    camera_data.clip_start = 0.01
    camera_data.clip_end = max(1000.0, extent * 12.0)
    camera_obj = bpy.data.objects.new("Trees2_ImpostorCamera", camera_data)
    scene.collection.objects.link(camera_obj)

    sun_data = bpy.data.lights.new("Trees2_ImpostorSun", "SUN")
    sun_data.energy = 2.1
    sun_data.angle = math.radians(18.0)
    sun_obj = bpy.data.objects.new("Trees2_ImpostorSun", sun_data)
    scene.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = (math.radians(38.0), math.radians(-18.0), math.radians(32.0))

    fill_data = bpy.data.lights.new("Trees2_ImpostorFill", "AREA")
    fill_data.energy = 650.0
    fill_data.shape = "DISK"
    fill_data.size = max(extent * 1.4, 2.0)
    fill_obj = bpy.data.objects.new("Trees2_ImpostorFill", fill_data)
    scene.collection.objects.link(fill_obj)
    fill_obj.location = center + Vector((-extent * 1.2, extent * 0.8, extent * 1.3))
    _look_at(fill_obj, center)
    return camera_obj, (sun_obj, fill_obj)


def _remove_object_and_data(obj):
    if not obj:
        return
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data and getattr(data, "users", 0) == 0:
        if isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)


def _copy_tile_into_atlas(destination, atlas_width, tile_pixels, tile_size, column, row, rows):
    dst_row = rows - 1 - row
    row_width = tile_size * 4
    for y in range(tile_size):
        src = y * row_width
        dst_y = dst_row * tile_size + y
        dst = (dst_y * atlas_width + column * tile_size) * 4
        destination[dst:dst + row_width] = tile_pixels[src:src + row_width]


def _make_impostor_material(atlas_image, views):
    mat = bpy.data.materials.new(name=f"Trees2_ImpostorMaterial_{atlas_image.name}")
    mat.use_nodes = True
    mat.use_backface_culling = True
    mat.surface_render_method = "DITHERED"
    mat.use_transparent_shadow = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexImage")
    tex.name = "Trees2 Impostor Atlas"
    tex.image = atlas_image
    tex.interpolation = "Linear"
    tex.extension = "CLIP"
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.82

    facing = nodes.new("ShaderNodeLayerWeight")
    cutoff = nodes.new("ShaderNodeMath")
    # Blender 5.2 Layer Weight Facing is 0 when face-on and approaches 1
    # toward grazing angles. Keep only cards inside roughly half a view step.
    cutoff.operation = "LESS_THAN"
    cutoff.inputs[1].default_value = 1.0 - math.cos((math.pi / max(views, 4)) * 1.04)
    alpha = nodes.new("ShaderNodeMath")
    alpha.operation = "MULTIPLY"
    links.new(facing.outputs["Facing"], cutoff.inputs[0])
    links.new(tex.outputs["Alpha"], alpha.inputs[0])
    links.new(cutoff.outputs[0], alpha.inputs[1])
    links.new(alpha.outputs[0], bsdf.inputs["Alpha"])
    return mat


def create_impostor_mesh(root, atlas_image, bounds_min, bounds_max, views, columns, rows, offset=None):
    old = [obj for obj in root.all_objects if obj.get("trees2_impostor")]
    for obj in old:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and getattr(data, "users", 0) == 0 and isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)

    center_xy = Vector(((bounds_min.x + bounds_max.x) * 0.5, (bounds_min.y + bounds_max.y) * 0.5, 0.0))
    width = max(bounds_max.x - bounds_min.x, bounds_max.y - bounds_min.y) * 1.035
    height = max(bounds_max.z - bounds_min.z, 0.01)
    verts = []
    faces = []
    face_uvs = []
    for index in range(views):
        azimuth = math.tau * index / views
        outward = Vector((math.cos(azimuth), math.sin(azimuth), 0.0))
        tangent = Vector((-outward.y, outward.x, 0.0))
        base = len(verts)
        verts.extend((
            -tangent * width * 0.5 + Vector((0.0, 0.0, 0.0)),
            tangent * width * 0.5 + Vector((0.0, 0.0, 0.0)),
            tangent * width * 0.5 + Vector((0.0, 0.0, height)),
            -tangent * width * 0.5 + Vector((0.0, 0.0, height)),
        ))
        faces.append((base, base + 1, base + 2, base + 3))
        u0, v0, u1, v1 = _atlas_uv(index, columns, rows)
        face_uvs.append(((u0, v0), (u1, v0), (u1, v1), (u0, v1)))

    mesh = bpy.data.meshes.new(f"Trees2_ImpostorMesh_{root.get('trees2_suffix', 'Tree')}")
    mesh.from_pydata([v[:] for v in verts], [], faces)
    uv = mesh.uv_layers.new(name="UVMap")
    for poly, coords in zip(mesh.polygons, face_uvs):
        for loop_index, coord in zip(poly.loop_indices, coords):
            uv.data[loop_index].uv = coord

    material = _make_impostor_material(atlas_image, views)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(f"Trees2_Impostor_LOD4_{root.get('trees2_suffix', 'Tree')}", mesh)
    root.objects.link(obj)
    obj.location = Vector((center_xy.x, center_xy.y, bounds_min.z)) + (Vector(offset) if offset else Vector((0.0, 0.0, 0.0)))
    obj["trees2_impostor"] = True
    obj["trees2_lod"] = "LOD4_IMPOSTOR"
    obj["trees2_impostor_views"] = views
    obj["trees2_impostor_columns"] = columns
    obj["trees2_impostor_rows"] = rows
    obj["trees2_impostor_atlas"] = atlas_image.filepath
    obj["trees2_triangle_estimate"] = views * 2
    obj["trees2_runtime_hint"] = "Select atlas frame by camera azimuth; each baked view spans 2*pi/views"
    return obj


def bake_impostor(context, root, advanced, billboard_offset=None):
    if not root:
        raise ValueError("No Trees 2.0 root collection supplied")

    scene = context.scene
    views = max(4, int(advanced.impostor_views))
    resolution = max(64, int(advanced.impostor_resolution))
    columns = max(1, int(math.ceil(math.sqrt(views))))
    rows = max(1, int(math.ceil(views / columns)))
    bounds_min, bounds_max = _tree_bounds(root, context)
    center = (bounds_min + bounds_max) * 0.5
    width = max(bounds_max.x - bounds_min.x, bounds_max.y - bounds_min.y, 0.01)
    height = max(bounds_max.z - bounds_min.z, 0.01)
    extent = max(width, height)
    ortho_scale = extent * (1.0 + advanced.impostor_padding * 2.0)
    distance = max(extent * 2.8, 10.0)

    output_dir = bpy.path.abspath(advanced.impostor_output_dir) if advanced.impostor_output_dir else ""
    if not output_dir:
        output_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else tempfile.gettempdir()
    os.makedirs(output_dir, exist_ok=True)
    suffix = root.get("trees2_suffix", "tree")
    atlas_path = os.path.join(output_dir, f"Trees2_Impostor_{suffix}_{views}v.png")

    saved = {
        "camera": scene.camera,
        "filepath": scene.render.filepath,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "resolution_percentage": scene.render.resolution_percentage,
        "film_transparent": scene.render.film_transparent,
        "file_format": scene.render.image_settings.file_format,
        "color_mode": scene.render.image_settings.color_mode,
    }
    hide_states = {obj.name: obj.hide_render for obj in scene.objects}
    tree_object_names = {obj.name for obj in root.all_objects}
    camera_obj = None
    lights = ()
    try:
        for obj in scene.objects:
            if obj.name not in tree_object_names:
                obj.hide_render = True
            elif obj.get("trees2_internal") or obj.get("trees2_impostor"):
                obj.hide_render = True
            else:
                obj.hide_render = False

        camera_obj, lights = _make_render_rig(scene, center, extent)
        camera_obj.hide_render = False
        for light in lights:
            light.hide_render = False
        scene.camera = camera_obj
        camera_obj.data.ortho_scale = ortho_scale
        scene.render.resolution_x = resolution
        scene.render.resolution_y = resolution
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"

        tile_buffers = []
        with tempfile.TemporaryDirectory(prefix="trees2_impostor_") as temp_dir:
            for index in range(views):
                azimuth = math.tau * index / views
                elevation = advanced.impostor_elevation
                outward = Vector((math.cos(azimuth) * math.cos(elevation), math.sin(azimuth) * math.cos(elevation), math.sin(elevation)))
                camera_obj.location = center + outward * distance
                _look_at(camera_obj, center)
                tile_path = os.path.join(temp_dir, f"view_{index:03d}.png")
                scene.render.filepath = tile_path
                bpy.ops.render.render(write_still=True)
                tile = bpy.data.images.load(tile_path, check_existing=False)
                try:
                    tile_buffers.append(list(tile.pixels[:]))
                finally:
                    bpy.data.images.remove(tile)

        atlas_width = columns * resolution
        atlas_height = rows * resolution
        pixels = [0.0] * (atlas_width * atlas_height * 4)
        for index, tile_pixels in enumerate(tile_buffers):
            _copy_tile_into_atlas(pixels, atlas_width, tile_pixels, resolution, index % columns, index // columns, rows)

        image_name = f"Trees2_ImpostorAtlas_{suffix}"
        existing = bpy.data.images.get(image_name)
        if existing:
            bpy.data.images.remove(existing)
        atlas_image = bpy.data.images.new(image_name, width=atlas_width, height=atlas_height, alpha=True)
        atlas_image.alpha_mode = "STRAIGHT"
        try:
            atlas_image.pixels.foreach_set(pixels)
        except Exception:
            atlas_image.pixels[:] = pixels
        atlas_image.update()
        atlas_image.filepath_raw = atlas_path
        atlas_image.file_format = "PNG"
        atlas_image.save()

        root["trees2_impostor_atlas"] = atlas_path
        root["trees2_impostor_views"] = views
        root["trees2_impostor_grid"] = json.dumps({"columns": columns, "rows": rows, "resolution": resolution})
        billboard = None
        if advanced.create_impostor_mesh:
            billboard = create_impostor_mesh(root, atlas_image, bounds_min, bounds_max, views, columns, rows, offset=billboard_offset)
        return atlas_image, billboard, atlas_path
    finally:
        scene.camera = saved["camera"]
        scene.render.filepath = saved["filepath"]
        scene.render.resolution_x = saved["resolution_x"]
        scene.render.resolution_y = saved["resolution_y"]
        scene.render.resolution_percentage = saved["resolution_percentage"]
        scene.render.film_transparent = saved["film_transparent"]
        scene.render.image_settings.file_format = saved["file_format"]
        scene.render.image_settings.color_mode = saved["color_mode"]
        for name, state in hide_states.items():
            obj = bpy.data.objects.get(name)
            if obj:
                obj.hide_render = state
        _remove_object_and_data(camera_obj)
        for light in lights:
            _remove_object_and_data(light)
