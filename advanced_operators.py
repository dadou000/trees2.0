import bpy
from mathutils import Vector

from . import generator, operators, stable_lods
from .impostor import bake_impostor


_ORIGINAL_LOD_EXECUTE = None
_LOD_PATCHED = False


def _active_tree_collection(context):
    obj = context.active_object
    if obj:
        name = obj.get("trees2_root_collection")
        if name:
            return bpy.data.collections.get(name)
        for collection in obj.users_collection:
            if collection.get("trees2_tree"):
                return collection
    return None


class TREES2_OT_BakeImpostor(bpy.types.Operator):
    bl_idname = "trees2.bake_impostor"
    bl_label = "Bake Multi-View Impostor"
    bl_description = "Render the selected tree from multiple directions, pack an RGBA atlas, and create a very-low-cost LOD4 impostor"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_tree_collection(context) is not None

    def execute(self, context):
        root = _active_tree_collection(context)
        advanced = context.scene.trees2_advanced_settings
        try:
            _atlas, billboard, path = bake_impostor(context, root, advanced)
        except Exception as exc:
            self.report({"ERROR"}, f"Impostor bake failed: {exc}")
            return {"CANCELLED"}
        if billboard:
            bpy.ops.object.select_all(action="DESELECT")
            billboard.hide_set(False)
            billboard.select_set(True)
            context.view_layer.objects.active = billboard
        self.report({"INFO"}, f"Baked {advanced.impostor_views} views to {path}")
        return {"FINISHED"}


def _advanced_lod_execute(self, context):
    """Generate nested LODs from one master skeleton and foliage population."""
    advanced = context.scene.trees2_advanced_settings
    settings = context.scene.trees2_settings
    old_lod = settings.lod
    origin = context.scene.cursor.location.copy()
    spacing = settings.height * 0.72
    lod0_root = None
    lod0_branch = None

    try:
        # Generate stochastic growth only once. All lower LODs are strict,
        # deterministic derivatives of this exact tree.
        settings.lod = "LOD0"
        master_branches, master_terminals = generator.generate_skeleton(settings)
        master_records = stable_lods.generate_master_foliage(settings, master_terminals)

        lods = ("LOD0", "LOD1", "LOD2", "LOD3")
        if not advanced.replace_lod4_with_impostor:
            lods = lods + ("LOD4",)

        for i, lod in enumerate(lods):
            settings.lod = lod
            branches, terminals = stable_lods.derive_lod_skeleton(master_branches, settings, lod)
            records = stable_lods.derive_lod_foliage(master_records, settings, lod)
            root, branch, _foliage = stable_lods.build_tree_from_data(
                context,
                settings,
                branches,
                terminals,
                records,
                location=origin + Vector((i * spacing, 0.0, 0.0)),
            )
            branch["trees2_master_branch_count"] = len(master_branches)
            branch["trees2_master_leaf_points"] = len(master_records)
            if lod == "LOD0":
                lod0_root = root
                lod0_branch = branch
    except Exception as exc:
        self.report({"ERROR"}, f"Stable LOD generation failed: {exc}")
        return {"CANCELLED"}
    finally:
        settings.lod = old_lod

    if not advanced.replace_lod4_with_impostor:
        if lod0_branch:
            context.view_layer.objects.active = lod0_branch
        self.report({"INFO"}, "Generated stable nested LOD0-LOD4 from one master tree")
        return {"FINISHED"}

    if not lod0_root:
        self.report({"ERROR"}, "Could not create LOD0 source for impostor")
        return {"CANCELLED"}

    try:
        _atlas, billboard, path = bake_impostor(
            context,
            lod0_root,
            advanced,
            billboard_offset=Vector((4.0 * spacing, 0.0, 0.0)),
        )
        if billboard:
            billboard["trees2_lod_set_preview"] = True
            billboard["trees2_lod_source"] = "LOD0_MASTER"
            bpy.ops.object.select_all(action="DESELECT")
            billboard.hide_set(False)
            billboard.select_set(True)
            context.view_layer.objects.active = billboard
        elif lod0_branch:
            context.view_layer.objects.active = lod0_branch
        self.report({"INFO"}, f"Generated stable LOD0-LOD3 + multi-view impostor LOD4: {path}")
    except Exception as exc:
        self.report({"WARNING"}, f"LOD0-LOD3 generated, but impostor bake failed: {exc}")
    return {"FINISHED"}


def _install_lod_patch():
    global _ORIGINAL_LOD_EXECUTE, _LOD_PATCHED
    if _LOD_PATCHED:
        return
    _ORIGINAL_LOD_EXECUTE = operators.TREES2_OT_GenerateLODSet.execute
    operators.TREES2_OT_GenerateLODSet.execute = _advanced_lod_execute
    _LOD_PATCHED = True


def _uninstall_lod_patch():
    global _LOD_PATCHED
    if not _LOD_PATCHED:
        return
    operators.TREES2_OT_GenerateLODSet.execute = _ORIGINAL_LOD_EXECUTE
    _LOD_PATCHED = False


CLASSES = (TREES2_OT_BakeImpostor,)


def register():
    _install_lod_patch()
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _uninstall_lod_patch()
