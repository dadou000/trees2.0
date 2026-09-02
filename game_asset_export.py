"""Organized two-mesh game-asset exporter for Trees 2.0.

Exports a selected generated tree as a compatibility glTF/GLB containing exactly
one wood mesh node and one realized foliage mesh node.  The authoring tree is not
modified: foliage realization happens into a temporary export mesh.

The exporter also writes an engine-independent runtime contract:

* branch_graph.json -- hierarchy, centerlines and response hints;
* foliage_bindings.bin/json -- compact card -> branch mapping;
* manifest.json -- stable paths, LOD entries and shader attribute names.

Multiple LODs exported with the same Asset Name are merged into the same asset
folder, so LOD0..LOD4 can be accumulated without manual file organization.
"""

import json
import os
import re
import shutil
import struct
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector


GENERATOR_VERSION = "0.9.4"
FOLIAGE_BINDING_STRUCT = struct.Struct("<IffffHH")


def _safe_component(value):
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    text = text.strip("._-")
    return text or "tree"


def _active_tree_collection(context):
    obj = context.active_object
    if not obj:
        return None
    name = obj.get("trees2_root_collection")
    return bpy.data.collections.get(name) if name else None


def _tree_objects(root):
    wood = None
    foliage = None
    if not root:
        return wood, foliage
    for obj in root.all_objects:
        if obj.get("trees2_internal"):
            continue
        if obj.get("trees2_foliage"):
            foliage = obj
        elif obj.type == "MESH" and obj.get("trees2_root_collection") == root.name:
            wood = obj
    return wood, foliage


def _source_collection(root):
    for child in root.children:
        if child.get("trees2_internal"):
            return child
    return None


def _attr(mesh, name):
    value = mesh.attributes.get(name)
    if value is None or value.domain != "POINT":
        return None
    return value


def _attr_scalar(mesh, name, index, default=0.0):
    attr = _attr(mesh, name)
    if attr is None or index >= len(attr.data):
        return default
    try:
        return attr.data[index].value
    except Exception:
        return default


def _attr_vector(mesh, name, index, default=(1.0, 1.0, 1.0)):
    attr = _attr(mesh, name)
    if attr is None or index >= len(attr.data):
        return Vector(default)
    try:
        return Vector(attr.data[index].vector)
    except Exception:
        return Vector(default)


def _attr_quaternion(mesh, name, index):
    attr = _attr(mesh, name)
    if attr is None or index >= len(attr.data):
        return Quaternion((1.0, 0.0, 0.0, 0.0))
    try:
        value = attr.data[index].value
        values = tuple(float(component) for component in value)
        if len(values) == 4:
            return Quaternion(values)
    except Exception:
        pass
    return Quaternion((1.0, 0.0, 0.0, 0.0))


def _ensure_export_float_attribute(mesh, export_name, source_name=None, values=None, default=0.0):
    if values is None:
        source = _attr(mesh, source_name) if source_name else None
        if source is not None:
            values = [float(getattr(item, "value", default)) for item in source.data]
        else:
            values = [float(default)] * len(mesh.vertices)

    existing = mesh.attributes.get(export_name)
    if existing is not None:
        mesh.attributes.remove(existing)
    attr = mesh.attributes.new(name=export_name, type="FLOAT", domain="POINT")
    for item, value in zip(attr.data, values):
        item.value = float(value)
    return attr


def _prepare_wood_export(original, name, collection):
    obj = original.copy()
    obj.data = original.data.copy()
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    collection.objects.link(obj)
    obj.matrix_world = Matrix.Identity(4)
    obj["trees2_surface_role"] = "wood"

    aliases = (
        ("_TREES2_BRANCH_ID", "trees2_branch_id", 0.0),
        ("_TREES2_BRANCH_T", "trees2_branch_t", 0.0),
        ("_TREES2_WIND_WEIGHT", "trees2_wind_weight", 0.0),
        ("_TREES2_WIND_PHASE", "trees2_wind_phase", 0.0),
        ("_TREES2_STIFFNESS", "trees2_stiffness", 1.0),
    )
    for export_name, source_name, default in aliases:
        _ensure_export_float_attribute(obj.data, export_name, source_name=source_name, default=default)
    return obj


def _source_cards(root):
    source = _source_collection(root)
    if source is None:
        return {}
    cards = {}
    for obj in source.objects:
        if obj.type != "MESH":
            continue
        index = int(obj.get("trees2_atlas_index", len(cards)))
        cards[index] = obj
    return cards


def _material_from_cards(cards):
    for obj in cards.values():
        if obj.data.materials:
            return obj.data.materials[0]
    return None


def _prepare_foliage_export(original, root, name, collection):
    """Realize foliage explicitly so branch mapping survives into export."""
    point_mesh = original.data
    cards = _source_cards(root)
    if not cards:
        raise RuntimeError("Leaf source cards are missing; regenerate the tree before game export")

    branch_id_attr = _attr(point_mesh, "trees2_source_branch_id")
    branch_t_attr = _attr(point_mesh, "trees2_source_branch_t")
    if branch_id_attr is None or branch_t_attr is None:
        raise RuntimeError("Tree has no runtime foliage mapping; regenerate it with Trees 2.0 0.9.4+")

    verts = []
    faces = []
    face_uvs = []
    branch_ids = []
    branch_ts = []
    wind_weights = []
    wind_phases = []
    stiffnesses = []
    atlas_values = []

    default_card = cards[min(cards.keys())]
    for point_index, point in enumerate(point_mesh.vertices):
        atlas_index = int(_attr_scalar(point_mesh, "trees2_atlas_index", point_index, 0))
        card_obj = cards.get(atlas_index, default_card)
        card_mesh = card_obj.data
        rotation = _attr_quaternion(point_mesh, "trees2_rotation", point_index)
        scale = _attr_vector(point_mesh, "trees2_scale", point_index)
        position = point.co

        branch_id = int(branch_id_attr.data[point_index].value)
        branch_t = float(branch_t_attr.data[point_index].value)
        wind = float(_attr_scalar(point_mesh, "trees2_wind_weight", point_index, 0.0))
        phase = float(_attr_scalar(point_mesh, "trees2_wind_phase", point_index, 0.0))
        stiffness = float(_attr_scalar(point_mesh, "trees2_stiffness", point_index, 1.0))

        vertex_offset = len(verts)
        for source_vertex in card_mesh.vertices:
            local = Vector((
                source_vertex.co.x * scale.x,
                source_vertex.co.y * scale.y,
                source_vertex.co.z * scale.z,
            ))
            verts.append(position + rotation @ local)
            branch_ids.append(float(branch_id))
            branch_ts.append(branch_t)
            wind_weights.append(wind)
            wind_phases.append(phase)
            stiffnesses.append(stiffness)
            atlas_values.append(float(atlas_index))

        uv_layer = card_mesh.uv_layers.active
        for polygon in card_mesh.polygons:
            faces.append(tuple(vertex_offset + vertex for vertex in polygon.vertices))
            if uv_layer is not None:
                face_uvs.append(tuple(tuple(uv_layer.data[loop].uv) for loop in polygon.loop_indices))
            else:
                face_uvs.append(tuple((0.0, 0.0) for _loop in polygon.loop_indices))

    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata([vertex[:] for vertex in verts], [], faces)
    for polygon in mesh.polygons:
        polygon.use_smooth = False

    uv = mesh.uv_layers.new(name="UVMap")
    for polygon, coords in zip(mesh.polygons, face_uvs):
        for loop_index, coordinate in zip(polygon.loop_indices, coords):
            uv.data[loop_index].uv = coordinate

    material = _material_from_cards(cards)
    if material is not None:
        mesh.materials.append(material)

    _ensure_export_float_attribute(mesh, "_TREES2_BRANCH_ID", values=branch_ids)
    _ensure_export_float_attribute(mesh, "_TREES2_BRANCH_T", values=branch_ts)
    _ensure_export_float_attribute(mesh, "_TREES2_WIND_WEIGHT", values=wind_weights)
    _ensure_export_float_attribute(mesh, "_TREES2_WIND_PHASE", values=wind_phases)
    _ensure_export_float_attribute(mesh, "_TREES2_STIFFNESS", values=stiffnesses)
    _ensure_export_float_attribute(mesh, "_TREES2_ATLAS_INDEX", values=atlas_values)

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.matrix_world = Matrix.Identity(4)
    obj["trees2_surface_role"] = "foliage"
    obj["trees2_foliage_realized_for_export"] = True
    return obj


def _walk_image_nodes(node_tree, output, visited):
    if node_tree is None or node_tree.as_pointer() in visited:
        return
    visited.add(node_tree.as_pointer())
    for node in node_tree.nodes:
        if node.type == "TEX_IMAGE" and getattr(node, "image", None) is not None:
            output[node.image.name_full] = node.image
        elif node.type == "GROUP" and getattr(node, "node_tree", None) is not None:
            _walk_image_nodes(node.node_tree, output, visited)


def _used_images(objects):
    images = {}
    for obj in objects:
        if obj.type != "MESH":
            continue
        for material in obj.data.materials:
            if material and material.use_nodes:
                _walk_image_nodes(material.node_tree, images, set())
    return list(images.values())


def _copy_textures(objects, texture_dir, asset_root):
    copied = []
    skipped = []
    texture_dir.mkdir(parents=True, exist_ok=True)
    used_names = set()

    for image in _used_images(objects):
        source_text = getattr(image, "filepath", "") or getattr(image, "filepath_raw", "")
        if not source_text:
            skipped.append({"image": image.name, "reason": "no external filepath"})
            continue
        source = Path(bpy.path.abspath(source_text))
        if not source.is_file():
            skipped.append({"image": image.name, "reason": "source file not found", "source": str(source)})
            continue

        stem = _safe_component(Path(source.name).stem)
        suffix = source.suffix or ".png"
        candidate = f"{stem}{suffix}"
        serial = 1
        while candidate.lower() in used_names:
            candidate = f"{stem}_{serial:02d}{suffix}"
            serial += 1
        used_names.add(candidate.lower())
        destination = texture_dir / candidate
        try:
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            copied.append({
                "image": image.name,
                "path": destination.relative_to(asset_root).as_posix(),
            })
        except Exception as exc:
            skipped.append({"image": image.name, "reason": str(exc), "source": str(source)})
    return copied, skipped


def _gltf_vector(values):
    # Blender local XYZ (Z-up) -> glTF/Godot-compatible XYZ (Y-up, -Z forward).
    return [float(values[0]), float(values[2]), -float(values[1])]


def _runtime_graph_for_export(raw_graph):
    graph = dict(raw_graph)
    graph["coordinate_system"] = "gltf_y_up"
    converted = []
    for source in raw_graph.get("branches", ()):
        branch = dict(source)
        branch["rest_position"] = _gltf_vector(source.get("rest_position", (0.0, 0.0, 0.0)))
        branch["rest_direction"] = _gltf_vector(source.get("rest_direction", (0.0, 0.0, 1.0)))
        branch["centerline"] = [
            [float(point[0]), float(point[2]), -float(point[1]), float(point[3])]
            for point in source.get("centerline", ())
        ]
        converted.append(branch)
    graph["branches"] = converted
    return graph


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _load_json(path, default=None):
    if not path.is_file():
        return {} if default is None else default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {} if default is None else default


def _write_runtime_metadata(root, foliage, runtime_dir, asset_root):
    graph_raw = root.get("trees2_branch_graph")
    if not graph_raw:
        raise RuntimeError("Tree has no runtime branch graph; regenerate it with Trees 2.0 0.9.4+")
    try:
        graph = json.loads(graph_raw)
    except Exception as exc:
        raise RuntimeError(f"Could not decode runtime branch graph: {exc}") from exc

    runtime_dir.mkdir(parents=True, exist_ok=True)
    graph_path = runtime_dir / "branch_graph.json"
    _write_json(graph_path, _runtime_graph_for_export(graph))

    mesh = foliage.data
    branch_attr = _attr(mesh, "trees2_source_branch_id")
    branch_t_attr = _attr(mesh, "trees2_source_branch_t")
    if branch_attr is None or branch_t_attr is None:
        raise RuntimeError("Tree foliage has no branch bindings; regenerate it with Trees 2.0 0.9.4+")

    binary_path = runtime_dir / "foliage_bindings.bin"
    with binary_path.open("wb") as handle:
        for index in range(len(mesh.vertices)):
            branch_id = int(branch_attr.data[index].value)
            encoded_id = branch_id if branch_id >= 0 else 0xFFFFFFFF
            branch_t = float(branch_t_attr.data[index].value)
            wind = float(_attr_scalar(mesh, "trees2_wind_weight", index, 0.0))
            phase = float(_attr_scalar(mesh, "trees2_wind_phase", index, 0.0))
            stiffness = float(_attr_scalar(mesh, "trees2_stiffness", index, 1.0))
            atlas = max(0, min(65535, int(_attr_scalar(mesh, "trees2_atlas_index", index, 0))))
            role = max(0, min(255, int(_attr_scalar(mesh, "trees2_assembly_role", index, 0))))
            flags = role
            handle.write(FOLIAGE_BINDING_STRUCT.pack(
                encoded_id,
                branch_t,
                wind,
                phase,
                stiffness,
                atlas,
                flags,
            ))

    descriptor = {
        "schema": "trees2.foliage_bindings/1",
        "record_count": len(mesh.vertices),
        "stride_bytes": FOLIAGE_BINDING_STRUCT.size,
        "endianness": "little",
        "binary": binary_path.name,
        "record_layout": [
            {"name": "branch_id", "type": "uint32", "offset": 0, "unbound": 4294967295},
            {"name": "branch_t", "type": "float32", "offset": 4},
            {"name": "wind_weight", "type": "float32", "offset": 8},
            {"name": "wind_phase", "type": "float32", "offset": 12},
            {"name": "stiffness", "type": "float32", "offset": 16},
            {"name": "atlas_index", "type": "uint16", "offset": 20},
            {"name": "flags", "type": "uint16", "offset": 22, "notes": "low byte stores foliage assembly role"},
        ],
    }
    descriptor_path = runtime_dir / "foliage_bindings.json"
    _write_json(descriptor_path, descriptor)

    return {
        "branch_graph": graph_path.relative_to(asset_root).as_posix(),
        "foliage_bindings": binary_path.relative_to(asset_root).as_posix(),
        "foliage_binding_schema": descriptor_path.relative_to(asset_root).as_posix(),
    }


def _supported_gltf_kwargs(proposed):
    try:
        properties = bpy.ops.export_scene.gltf.get_rna_type().properties
        supported = {prop.identifier for prop in properties}
        return {key: value for key, value in proposed.items() if key in supported}
    except Exception:
        return proposed


def _export_gltf(filepath, export_format):
    if not hasattr(bpy.ops.export_scene, "gltf"):
        raise RuntimeError("Blender glTF exporter is unavailable")

    proposed = {
        "filepath": str(filepath),
        "export_format": export_format,
        "use_selection": True,
        "export_apply": True,
        "export_attributes": True,
        "export_extras": True,
        "export_texcoords": True,
        "export_normals": True,
        "export_tangents": True,
        "export_materials": "EXPORT",
        "export_cameras": False,
        "export_lights": False,
        "export_animations": False,
        "export_yup": True,
    }
    result = bpy.ops.export_scene.gltf(**_supported_gltf_kwargs(proposed))
    if "FINISHED" not in result:
        raise RuntimeError("Blender glTF exporter did not finish")


def _snapshot_selection(context):
    return {
        "selected": [obj.name for obj in context.selected_objects],
        "active": context.view_layer.objects.active.name if context.view_layer.objects.active else None,
    }


def _restore_selection(context, snapshot):
    bpy.ops.object.select_all(action="DESELECT")
    for name in snapshot.get("selected", ()):
        obj = bpy.data.objects.get(name)
        if obj and context.view_layer.objects.get(name):
            obj.select_set(True)
    active_name = snapshot.get("active")
    active = bpy.data.objects.get(active_name) if active_name else None
    if active and context.view_layer.objects.get(active.name):
        context.view_layer.objects.active = active


def _remove_temp_collection(collection):
    if collection is None:
        return
    for obj in list(collection.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and getattr(data, "users", 1) == 0 and isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
    if collection.name in bpy.data.collections:
        bpy.data.collections.remove(collection)


def _resolved_paths(root, settings):
    source_settings = {}
    try:
        source_settings = json.loads(root.get("trees2_settings", "{}"))
    except Exception:
        pass

    species = str(source_settings.get("species_preset", root.get("trees2_species", "GENERIC")))
    seed = int(source_settings.get("seed", root.get("trees2_seed", 0)))
    lod = str(source_settings.get("lod", root.get("trees2_lod", "LOD0")))
    auto_name = f"{species.lower()}_{seed:08d}"
    asset_name = _safe_component(settings.asset_name or auto_name)

    root_path = Path(bpy.path.abspath(settings.output_root)).expanduser()
    if settings.organize_by_species:
        root_path = root_path / _safe_component(species.lower())
    asset_root = root_path / asset_name
    geometry_dir = asset_root / "geometry" / lod
    runtime_dir = asset_root / "runtime" / lod
    texture_dir = asset_root / "textures"
    return species, seed, lod, asset_name, asset_root, geometry_dir, runtime_dir, texture_dir, source_settings


def export_selected_tree(context):
    root = _active_tree_collection(context)
    if root is None:
        raise RuntimeError("Select a Trees 2.0 wood or foliage object first")
    wood, foliage = _tree_objects(root)
    if wood is None or foliage is None:
        raise RuntimeError("Selected Trees 2.0 tree must contain both wood and foliage")

    settings = context.scene.trees2_game_asset
    species, seed, lod, asset_name, asset_root, geometry_dir, runtime_dir, texture_dir, source_settings = _resolved_paths(root, settings)
    geometry_dir.mkdir(parents=True, exist_ok=True)
    asset_root.mkdir(parents=True, exist_ok=True)

    if settings.write_runtime_metadata:
        if not root.get("trees2_branch_graph"):
            raise RuntimeError("This tree predates the runtime backend. Regenerate it, then export again")
        if _attr(foliage.data, "trees2_source_branch_id") is None or _attr(foliage.data, "trees2_source_branch_t") is None:
            raise RuntimeError("This tree has no foliage branch mapping. Regenerate it, then export again")

    extension = ".glb" if settings.export_format == "GLB" else ".gltf"
    geometry_path = geometry_dir / f"{asset_name}_{lod}{extension}"

    snapshot = _snapshot_selection(context)
    temp = bpy.data.collections.new(f"Trees2_Export_{asset_name}_{lod}")
    context.scene.collection.children.link(temp)
    export_objects = []

    try:
        wood_export = _prepare_wood_export(wood, f"{asset_name}_{lod}_wood", temp)
        foliage_export = _prepare_foliage_export(foliage, root, f"{asset_name}_{lod}_foliage", temp)
        export_objects = [wood_export, foliage_export]

        bpy.ops.object.select_all(action="DESELECT")
        for obj in export_objects:
            obj.hide_set(False)
            obj.hide_render = False
            obj.select_set(True)
        context.view_layer.objects.active = wood_export
        _export_gltf(geometry_path, settings.export_format)

        runtime_paths = {}
        if settings.write_runtime_metadata:
            runtime_paths = _write_runtime_metadata(root, foliage, runtime_dir, asset_root)

        copied_textures = []
        skipped_textures = []
        if settings.copy_source_textures:
            copied_textures, skipped_textures = _copy_textures(export_objects, texture_dir, asset_root)

        manifest_path = asset_root / "manifest.json"
        manifest = _load_json(manifest_path, {})
        if manifest.get("schema") != "trees2.game_asset/1":
            manifest = {
                "schema": "trees2.game_asset/1",
                "asset_name": asset_name,
                "species": species,
                "seed": seed,
                "two_mesh_contract": True,
                "coordinate_system": "gltf_y_up",
                "generator": {"name": "Trees 2.0", "version": GENERATOR_VERSION},
                "lods": {},
            }

        manifest["asset_name"] = asset_name
        manifest["species"] = species
        manifest["seed"] = seed
        manifest["generator"] = {"name": "Trees 2.0", "version": GENERATOR_VERSION}
        manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["attribute_contract"] = {
            "wood": {
                "branch_id": "_TREES2_BRANCH_ID",
                "branch_t": "_TREES2_BRANCH_T",
                "wind_weight": "_TREES2_WIND_WEIGHT",
                "wind_phase": "_TREES2_WIND_PHASE",
                "stiffness": "_TREES2_STIFFNESS",
            },
            "foliage": {
                "support_branch_id": "_TREES2_BRANCH_ID",
                "attachment_t": "_TREES2_BRANCH_T",
                "wind_weight": "_TREES2_WIND_WEIGHT",
                "wind_phase": "_TREES2_WIND_PHASE",
                "stiffness": "_TREES2_STIFFNESS",
                "atlas_index": "_TREES2_ATLAS_INDEX",
            },
            "sidecars_authoritative": True,
        }
        manifest["source_textures"] = copied_textures
        if skipped_textures:
            manifest["texture_copy_warnings"] = skipped_textures
        else:
            manifest.pop("texture_copy_warnings", None)

        manifest.setdefault("lods", {})[lod] = {
            "geometry": geometry_path.relative_to(asset_root).as_posix(),
            "format": settings.export_format,
            "nodes": {
                "wood": wood_export.name,
                "foliage": foliage_export.name,
            },
            "runtime": runtime_paths,
            "counts": {
                "branches": int(wood.get("trees2_branch_count", 0)),
                "terminal_branches": int(wood.get("trees2_terminal_count", 0)),
                "foliage_cards": len(foliage.data.vertices),
                "wood_vertices": len(wood.data.vertices),
                "exported_foliage_vertices": len(foliage_export.data.vertices),
            },
            "source_settings": source_settings,
        }
        _write_json(manifest_path, manifest)

        return {
            "asset_root": str(asset_root),
            "geometry": str(geometry_path),
            "manifest": str(manifest_path),
            "lod": lod,
            "asset_name": asset_name,
        }
    finally:
        _remove_temp_collection(temp)
        _restore_selection(context, snapshot)


class TREES2_OT_ExportGameAsset(bpy.types.Operator):
    bl_idname = "trees2.export_game_asset"
    bl_label = "Export Selected Game Asset"
    bl_description = "Export the selected tree as organized two-mesh glTF plus GPU runtime branch/foliage metadata"

    @classmethod
    def poll(cls, context):
        return _active_tree_collection(context) is not None

    def execute(self, context):
        if context.mode != "OBJECT":
            self.report({"ERROR"}, "Game asset export requires Object Mode")
            return {"CANCELLED"}
        try:
            result = export_selected_tree(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {result['asset_name']} {result['lod']} to {result['asset_root']}")
        return {"FINISHED"}


CLASSES = (TREES2_OT_ExportGameAsset,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
