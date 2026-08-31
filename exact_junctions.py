import bmesh
import bpy

from . import advanced_growth, generator


_PREVIOUS_BRANCH_MESH = None
_PREVIOUS_BARK_MATERIAL = None
_INSTALLED = False


def _lod_index(lod):
    try:
        return int(str(lod).replace("LOD", ""))
    except Exception:
        return 0


def _advanced_settings():
    scene = getattr(bpy.context, "scene", None)
    return getattr(scene, "trees2_advanced_settings", None) if scene else None


def _remove_object(obj):
    if not obj:
        return
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data and getattr(data, "users", 0) == 0 and isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)


def _remove_mesh_if_unused(mesh):
    if mesh and getattr(mesh, "users", 0) == 0 and mesh.name in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)


def _seal_mesh(mesh):
    """Close every boundary loop so each branch piece is a valid Boolean solid."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        boundary = [edge for edge in bm.edges if edge.is_boundary]
        if boundary:
            bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()


def _capture_reference(branches, settings, bark_material, suffix, collection):
    base_builder = advanced_growth._ORIGINAL_BRANCH_MESH
    reference = base_builder(collection, branches, settings, bark_material, f"{suffix}_Reference")
    positions = [vertex.co.copy() for vertex in reference.data.vertices]
    captured = advanced_growth._capture_point_attributes(reference.data)
    _remove_object(reference)
    return positions, captured


def _make_piece(collection, branch, settings, bark_material, suffix):
    base_builder = advanced_growth._ORIGINAL_BRANCH_MESH
    obj = base_builder(collection, [branch], settings, bark_material, suffix)
    _seal_mesh(obj.data)
    return obj


def _trunk_bounds(trunk):
    z_values = [point.z for point, _radius in trunk.get("points", ())]
    if not z_values:
        return 0.0, 0.0
    return min(z_values), max(z_values)


def _mesh_preserves_trunk(mesh, trunk_min_z, trunk_max_z):
    """Reject Boolean results that silently delete/collapse the trunk."""
    if mesh is None or len(mesh.vertices) < 8 or len(mesh.polygons) < 4:
        return False

    z_values = [vertex.co.z for vertex in mesh.vertices]
    if not z_values:
        return False
    result_min = min(z_values)
    result_max = max(z_values)
    trunk_span = max(trunk_max_z - trunk_min_z, 1e-5)
    tolerance = max(0.03 * trunk_span, 0.02)

    if result_min > trunk_min_z + tolerance:
        return False
    if result_max < trunk_max_z - tolerance:
        return False
    if result_max - result_min < trunk_span * 0.92:
        return False

    # Require actual geometry near both the root and the upper trunk, not just
    # a stray vertex from another branch that happens to match the Z extent.
    base_limit = trunk_min_z + trunk_span * 0.08
    top_limit = trunk_max_z - trunk_span * 0.08
    base_vertices = sum(1 for vertex in mesh.vertices if vertex.co.z <= base_limit)
    top_vertices = sum(1 for vertex in mesh.vertices if vertex.co.z >= top_limit)
    return base_vertices >= 3 and top_vertices >= 1


def _restore_mesh_backup(target, backup, damaged_mesh):
    target.data = backup
    _remove_mesh_if_unused(damaged_mesh)


def _apply_union(target, operand, label, trunk_min_z, trunk_max_z):
    """Union one closed branch solid and verify the trunk survived intact."""
    backup = target.data.copy()
    damaged_mesh = target.data

    modifier = target.modifiers.new(name=label, type="BOOLEAN")
    modifier.operation = "UNION"
    modifier.object = operand
    if hasattr(modifier, "solver"):
        modifier.solver = "EXACT"
    if hasattr(modifier, "use_self"):
        modifier.use_self = False
    if hasattr(modifier, "use_hole_tolerant"):
        modifier.use_hole_tolerant = True

    bpy.ops.object.select_all(action="DESELECT")
    target.hide_set(False)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target

    try:
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        if not _mesh_preserves_trunk(target.data, trunk_min_z, trunk_max_z):
            failed_mesh = target.data
            _restore_mesh_backup(target, backup, failed_mesh)
            raise RuntimeError("Boolean union failed trunk-survival validation")
        _remove_mesh_if_unused(backup)
    except Exception:
        if modifier.name in target.modifiers:
            target.modifiers.remove(modifier)
        if target.data is not backup:
            current = target.data
            _restore_mesh_backup(target, backup, current)
        raise


def _join_objects(target, objects):
    objects = [obj for obj in objects if obj and obj.name in bpy.data.objects]
    if not objects:
        return
    bpy.ops.object.select_all(action="DESELECT")
    target.hide_set(False)
    target.select_set(True)
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.join()


def _object_exists(obj):
    if obj is None:
        return False
    try:
        return obj.name in bpy.data.objects
    except ReferenceError:
        return False


def _restore_selection(previous_active, previous_selected, target):
    bpy.ops.object.select_all(action="DESELECT")
    valid_selected = [obj for obj in previous_selected if _object_exists(obj)]
    for obj in valid_selected:
        obj.select_set(True)
    if _object_exists(previous_active):
        bpy.context.view_layer.objects.active = previous_active
    elif _object_exists(target):
        target.select_set(True)
        bpy.context.view_layer.objects.active = target


def _exact_boolean_branch_mesh(collection, branches, settings, bark_material, suffix):
    advanced = _advanced_settings()
    if (
        not advanced
        or advanced.junction_mode != "EXACT_BOOLEAN"
        or _lod_index(settings.lod) > advanced.junction_boolean_lod_max
        or not branches
    ):
        return _PREVIOUS_BRANCH_MESH(collection, branches, settings, bark_material, suffix)

    if advanced_growth._ORIGINAL_BRANCH_MESH is None:
        return _PREVIOUS_BRANCH_MESH(collection, branches, settings, bark_material, suffix)

    previous_active = bpy.context.view_layer.objects.active
    previous_selected = list(bpy.context.selected_objects)
    target = None
    fallback_objects = []
    exact_count = 0
    failed_count = 0

    try:
        reference_positions, captured = _capture_reference(
            branches, settings, bark_material, suffix, collection
        )

        trunk = min(branches, key=lambda b: (b.get("level", 0), b.get("id", 0)))
        trunk_min_z, trunk_max_z = _trunk_bounds(trunk)
        target = _make_piece(
            collection, trunk, settings, bark_material, f"{suffix}_ExactTrunk"
        )
        target.name = f"Trees2_Branches_{suffix}"
        target.data.name = f"Trees2_Branches_{suffix}"

        if not _mesh_preserves_trunk(target.data, trunk_min_z, trunk_max_z):
            raise RuntimeError("Initial sealed trunk failed trunk-survival validation")

        children = [branch for branch in branches if branch is not trunk]
        children.sort(key=lambda b: (b.get("level", 0), b.get("id", 0)))

        max_level = max(1, int(advanced.junction_boolean_level_max))
        for branch in children:
            level = int(branch.get("level", 1))
            piece = _make_piece(
                collection,
                branch,
                settings,
                bark_material,
                f"{suffix}_BooleanPiece_{branch.get('id', 0):04d}",
            )

            if level > max_level:
                fallback_objects.append(piece)
                continue

            try:
                _apply_union(
                    target,
                    piece,
                    f"Trees2 Exact Junction {branch.get('id', 0):04d}",
                    trunk_min_z,
                    trunk_max_z,
                )
                exact_count += 1
                _remove_object(piece)
            except Exception:
                # A Boolean is allowed to fail locally, but never to damage the
                # trunk. Keep that branch as a safe collar/intersection fallback.
                failed_count += 1
                fallback_objects.append(piece)

        _join_objects(target, fallback_objects)
        fallback_count = len(fallback_objects)

        mesh = target.data
        if not _mesh_preserves_trunk(mesh, trunk_min_z, trunk_max_z):
            raise RuntimeError("Final exact-junction mesh failed trunk-survival validation")
        if not mesh.materials:
            mesh.materials.append(bark_material)
        for polygon in mesh.polygons:
            polygon.use_smooth = True

        if advanced.reproject_branch_attributes:
            advanced_growth._reproject_attributes(mesh, reference_positions, captured)
        advanced_growth._fallback_uv(mesh, settings)

        target["trees2_junction_mode"] = "EXACT_BOOLEAN"
        target["trees2_exact_boolean_junctions"] = exact_count
        target["trees2_collar_fallback_branches"] = fallback_count
        target["trees2_boolean_failures"] = failed_count
        target["trees2_boolean_level_max"] = max_level
        target["trees2_boolean_lod_max"] = int(advanced.junction_boolean_lod_max)
        target["trees2_trunk_validated"] = True
        return target
    except Exception as exc:
        if _object_exists(target):
            _remove_object(target)
        for obj in fallback_objects:
            if _object_exists(obj):
                _remove_object(obj)
        fallback = _PREVIOUS_BRANCH_MESH(
            collection, branches, settings, bark_material, suffix
        )
        fallback["trees2_junction_mode"] = "EXACT_BOOLEAN_FAILED"
        fallback["trees2_junction_error"] = str(exc)
        fallback["trees2_trunk_validated"] = False
        return fallback
    finally:
        _restore_selection(previous_active, previous_selected, target)


def _exact_bark_material(settings, suffix):
    mat = _PREVIOUS_BARK_MATERIAL(settings, suffix)
    advanced = _advanced_settings()
    if (
        not advanced
        or advanced.junction_mode != "EXACT_BOOLEAN"
        or (not settings.bark_image and not settings.bark_normal_image)
    ):
        return mat

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    texcoord = nodes.new("ShaderNodeTexCoord")
    texcoord.name = "Trees2 Exact Junction Coordinates"
    mapping = nodes.new("ShaderNodeMapping")
    mapping.name = "Trees2 Exact Bark Box Mapping"

    # Generated coordinates are normalized to the full tree bounding box,
    # which badly stretches bark on long/narrow limbs. Object coordinates use
    # actual local units, preserving roughly constant texel scale everywhere.
    repeat = max(0.10, float(settings.bark_uv_scale))
    mapping.inputs["Scale"].default_value = (repeat, repeat, repeat)
    links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])

    # Every PBR map must use exactly the same projection. Previously only color
    # and normal were box-projected while roughness/height/AO still sampled UVs,
    # producing mismatched highlights that looked metallic.
    for name in (
        "Bark Color",
        "Bark AO",
        "Bark Roughness",
        "Bark Normal",
        "Bark Height",
    ):
        texture = nodes.get(name)
        if not texture:
            continue
        texture.projection = "BOX"
        texture.projection_blend = 0.32
        links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
    return mat


def install():
    global _PREVIOUS_BRANCH_MESH, _PREVIOUS_BARK_MATERIAL, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_BRANCH_MESH = generator.create_branch_mesh
    _PREVIOUS_BARK_MATERIAL = generator.create_bark_material
    generator.create_branch_mesh = _exact_boolean_branch_mesh
    generator.create_bark_material = _exact_bark_material
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.create_branch_mesh = _PREVIOUS_BRANCH_MESH
    generator.create_bark_material = _PREVIOUS_BARK_MATERIAL
    _INSTALLED = False
