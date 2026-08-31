import random

import bpy

from .generator import build_tree, remove_tree_collection


def _active_tree_collection(context):
    obj = context.active_object
    if obj:
        name = obj.get("trees2_root_collection")
        if name:
            return bpy.data.collections.get(name)
    return None


class TREES2_OT_CreateTree(bpy.types.Operator):
    bl_idname = "trees2.create_tree"
    bl_label = "Create Procedural Tree"
    bl_description = "Generate a game-ready procedural tree at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.trees2_settings
        _, branch_obj, _ = build_tree(context, settings)
        self.report({"INFO"}, f"Tree generated: {branch_obj.get('trees2_branch_count', 0)} branches, {branch_obj.get('trees2_leaf_points', 0)} foliage instances")
        return {"FINISHED"}


class TREES2_OT_RegenerateTree(bpy.types.Operator):
    bl_idname = "trees2.regenerate_tree"
    bl_label = "Regenerate Selected Tree"
    bl_description = "Replace the selected Trees 2.0 tree using the current panel settings"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_tree_collection(context) is not None

    def execute(self, context):
        root = _active_tree_collection(context)
        if not root:
            return {"CANCELLED"}
        location = context.active_object.location.copy()
        remove_tree_collection(root)
        build_tree(context, context.scene.trees2_settings, location=location)
        return {"FINISHED"}


class TREES2_OT_RandomizeSeed(bpy.types.Operator):
    bl_idname = "trees2.randomize_seed"
    bl_label = "Randomize Seed"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context.scene.trees2_settings.seed = random.SystemRandom().randint(0, 2_147_483_647)
        return {"FINISHED"}


class TREES2_OT_GenerateLODSet(bpy.types.Operator):
    bl_idname = "trees2.generate_lod_set"
    bl_label = "Generate LOD Set"
    bl_description = "Generate LOD0-LOD3 versions side by side for inspection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.trees2_settings
        old_lod = settings.lod
        origin = context.scene.cursor.location.copy()
        spacing = settings.height * 0.72
        try:
            for i, lod in enumerate(("LOD0", "LOD1", "LOD2", "LOD3")):
                settings.lod = lod
                build_tree(context, settings, location=origin + (i * spacing, 0.0, 0.0))
        finally:
            settings.lod = old_lod
        return {"FINISHED"}


CLASSES = (
    TREES2_OT_CreateTree,
    TREES2_OT_RegenerateTree,
    TREES2_OT_RandomizeSeed,
    TREES2_OT_GenerateLODSet,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
