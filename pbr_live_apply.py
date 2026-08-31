import bpy

from . import generator, procedural_pbr


_PREVIOUS_GENERATE = None
_INSTALLED = False


def _walk_collections(root):
    yield root
    for child in root.children:
        yield from _walk_collections(child)


def _active_tree_root(context):
    candidates = []
    if context.active_object is not None:
        candidates.append(context.active_object)
    candidates.extend(obj for obj in context.selected_objects if obj not in candidates)

    for obj in candidates:
        root_name = obj.get("trees2_root_collection")
        if root_name:
            root = bpy.data.collections.get(root_name)
            if root is not None:
                return root
    return None


def _source_collection(root):
    for collection in _walk_collections(root):
        if collection is root:
            continue
        if collection.name.startswith("Trees2_Sources_") or collection.get("trees2_internal", False):
            return collection
    return None


def _branch_objects(root):
    result = []
    seen = set()
    for collection in _walk_collections(root):
        for obj in collection.objects:
            if obj.name in seen:
                continue
            seen.add(obj.name)
            if not isinstance(getattr(obj, "data", None), bpy.types.Mesh):
                continue
            if obj.get("trees2_branch_count") is not None or obj.name.startswith("Trees2_Branches_"):
                result.append(obj)
    return result


def _remove_source_cards(source_collection):
    removed_meshes = []
    for obj in list(source_collection.objects):
        if obj.get("trees2_atlas_index") is None and not obj.name.startswith("Trees2_Card_"):
            continue
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if isinstance(data, bpy.types.Mesh):
            removed_meshes.append(data)

    for mesh in removed_meshes:
        if mesh.users == 0 and mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)


def _replace_object_material(obj, material):
    if not isinstance(getattr(obj, "data", None), bpy.types.Mesh):
        return
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0


def _cleanup_unused_tree_materials():
    for material in list(bpy.data.materials):
        if material.users != 0:
            continue
        if material.name.startswith("Trees2_Bark_") or material.name.startswith("Trees2_Leaves_"):
            bpy.data.materials.remove(material)


def _tag_viewports(context):
    try:
        context.view_layer.update()
    except Exception:
        pass
    screen = getattr(context, "screen", None)
    if screen is not None:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def apply_current_pbr_to_active_tree(context):
    """Apply current Trees 2.0 texture settings to the selected generated tree.

    This deliberately does not regenerate the skeleton. Bark materials are
    replaced on the existing woody mesh, while the hidden foliage-card source
    collection is rebuilt so its UV cells/count match a newly generated atlas.
    """
    root = _active_tree_root(context)
    if root is None:
        return {"applied": False, "reason": "No generated Trees 2.0 tree is selected"}

    settings = context.scene.trees2_settings
    suffix = str(root.get("trees2_suffix", root.name.replace("Trees2_Tree_", "")))
    branch_objects = _branch_objects(root)
    source_collection = _source_collection(root)

    bark_material = None
    if branch_objects:
        bark_material = generator.create_bark_material(settings, f"{suffix}_LivePBR")
        for branch_obj in branch_objects:
            _replace_object_material(branch_obj, bark_material)
            branch_obj["trees2_live_pbr"] = True

    leaf_material = None
    cards_created = 0
    if source_collection is not None:
        _remove_source_cards(source_collection)
        if settings.leaf_image is not None:
            leaf_material = generator.create_leaf_material(settings, f"{suffix}_LivePBR")
            cards = generator.create_leaf_sources(
                source_collection,
                settings,
                leaf_material,
                f"{suffix}_LivePBR",
            )
            cards_created = len(cards)

    root["trees2_live_pbr"] = True
    root["trees2_live_pbr_species"] = str(settings.species_preset)
    root["trees2_live_pbr_atlas_columns"] = int(settings.atlas_columns)
    root["trees2_live_pbr_atlas_rows"] = int(settings.atlas_rows)
    root["trees2_live_pbr_variants"] = int(settings.atlas_variants)

    _cleanup_unused_tree_materials()
    _tag_viewports(context)
    return {
        "applied": True,
        "root": root.name,
        "branch_objects": len(branch_objects),
        "cards_created": cards_created,
    }


def _generate_and_apply(context, species=None):
    result = _PREVIOUS_GENERATE(context, species)
    pbr = context.scene.trees2_pbr_settings
    if pbr.auto_assign:
        live = apply_current_pbr_to_active_tree(context)
        result["live_apply"] = live
    return result


class TREES2_OT_ApplyCurrentPBR(bpy.types.Operator):
    bl_idname = "trees2.apply_current_pbr"
    bl_label = "Apply PBR to Selected Tree"
    bl_description = "Apply the current leaf and bark texture settings to the selected Trees 2.0 tree without regenerating its geometry"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        result = apply_current_pbr_to_active_tree(context)
        if not result.get("applied"):
            self.report({"WARNING"}, result.get("reason", "Could not apply PBR textures"))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Applied PBR to {result['root']} ({result['cards_created']} foliage atlas sources)",
        )
        return {"FINISHED"}


CLASSES = (TREES2_OT_ApplyCurrentPBR,)


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = procedural_pbr.generate_species_pbr
    procedural_pbr.generate_species_pbr = _generate_and_apply
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    procedural_pbr.generate_species_pbr = _PREVIOUS_GENERATE
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _INSTALLED = False
