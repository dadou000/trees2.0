import json
import random

import bpy

from .generator import build_tree, remove_tree_collection
from .pbr_profiles import species_profile
from .presets import apply_preset
from .species_appearance import appearance_profile


def _active_tree_collection(context):
    obj = context.active_object
    if obj:
        name = obj.get("trees2_root_collection")
        if name:
            return bpy.data.collections.get(name)
    return None


def _tree_objects(root):
    branch = None
    foliage = None
    if not root:
        return branch, foliage
    for obj in root.all_objects:
        if obj.get("trees2_internal"):
            continue
        if obj.get("trees2_foliage"):
            foliage = obj
        elif obj.type == "MESH" and obj.get("trees2_root_collection") == root.name:
            branch = obj
    return branch, foliage


def _apply_species_colors(settings, species):
    appearance = appearance_profile(species, species_profile(species))
    leaf = appearance.get("default_leaf_tint")
    bark = appearance.get("default_bark_tint")
    if leaf and appearance.get("leaf_shape") != "NONE":
        settings.leaf_tint = (float(leaf[0]), float(leaf[1]), float(leaf[2]), 1.0)
    if bark:
        settings.bark_color = (float(bark[0]), float(bark[1]), float(bark[2]), 1.0)
    settings.pbr_respect_tree_colors = True
    return appearance


class TREES2_OT_ApplyPreset(bpy.types.Operator):
    bl_idname = "trees2.apply_preset"
    bl_label = "Apply Species Preset"
    bl_description = "Apply the selected species structure, correct foliage/trunk colors and morphology defaults while keeping texture assignments and seed"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.trees2_settings
        if not apply_preset(settings, settings.species_preset):
            self.report({"WARNING"}, "Unknown Trees 2.0 preset")
            return {"CANCELLED"}
        appearance = _apply_species_colors(settings, settings.species_preset)
        self.report(
            {"INFO"},
            f"Applied {settings.species_preset.title()} preset - {appearance.get('morphology_label', 'species foliage')}",
        )
        return {"FINISHED"}


class TREES2_OT_CreateTree(bpy.types.Operator):
    bl_idname = "trees2.create_tree"
    bl_label = "Create Procedural Tree"
    bl_description = "Generate a game-ready procedural tree at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.trees2_settings
        _, branch_obj, _ = build_tree(context, settings)
        self.report({"INFO"}, f"Tree: {branch_obj.get('trees2_branch_count', 0)} branches, {branch_obj.get('trees2_leaf_points', 0)} foliage instances")
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
        branch, foliage = _tree_objects(root)
        reference = branch or foliage or context.active_object
        location = reference.location.copy() if reference else context.scene.cursor.location.copy()
        remove_tree_collection(root)
        build_tree(context, context.scene.trees2_settings, location=location)
        return {"FINISHED"}


class TREES2_OT_LoadTreeSettings(bpy.types.Operator):
    bl_idname = "trees2.load_tree_settings"
    bl_label = "Load Selected Tree Settings"
    bl_description = "Load the saved generator parameters from the selected Trees 2.0 tree into the sidebar"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_tree_collection(context) is not None

    def execute(self, context):
        root = _active_tree_collection(context)
        raw = root.get("trees2_settings") if root else None
        if not raw:
            self.report({"WARNING"}, "Selected tree has no saved settings snapshot")
            return {"CANCELLED"}
        try:
            values = json.loads(raw)
        except Exception:
            self.report({"ERROR"}, "Could not decode the tree settings snapshot")
            return {"CANCELLED"}

        settings = context.scene.trees2_settings
        loaded = 0
        for key, value in values.items():
            if hasattr(settings, key):
                try:
                    setattr(settings, key, value)
                    loaded += 1
                except Exception:
                    pass
        self.report({"INFO"}, f"Loaded {loaded} generator parameters")
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
    bl_description = "Generate LOD0-LOD4 versions side by side for visual and performance inspection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.trees2_settings
        old_lod = settings.lod
        origin = context.scene.cursor.location.copy()
        spacing = settings.height * 0.80
        try:
            for i, lod in enumerate(("LOD0", "LOD1", "LOD2", "LOD3", "LOD4")):
                settings.lod = lod
                build_tree(context, settings, location=origin + (i * spacing, 0.0, 0.0))
        finally:
            settings.lod = old_lod
        return {"FINISHED"}


class TREES2_OT_BakeFoliage(bpy.types.Operator):
    bl_idname = "trees2.bake_foliage"
    bl_label = "Bake Foliage for Export"
    bl_description = "Apply the foliage Geometry Nodes modifier so leaf cards become real mesh geometry"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = _active_tree_collection(context)
        _, foliage = _tree_objects(root)
        return foliage is not None and bool(foliage.modifiers)

    def execute(self, context):
        root = _active_tree_collection(context)
        branch, foliage = _tree_objects(root)
        if not foliage or not foliage.modifiers:
            return {"CANCELLED"}

        previous_active = context.view_layer.objects.active
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        foliage.hide_set(False)
        foliage.select_set(True)
        context.view_layer.objects.active = foliage

        modifier_name = foliage.modifiers[0].name
        try:
            bpy.ops.object.modifier_apply(modifier=modifier_name)
        except RuntimeError as exc:
            self.report({"ERROR"}, f"Could not apply foliage modifier: {exc}")
            return {"CANCELLED"}

        root["trees2_foliage_baked"] = True
        foliage["trees2_foliage_baked"] = True

        for child in list(root.children):
            if child.get("trees2_internal"):
                for obj in list(child.objects):
                    data = obj.data
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if data and getattr(data, "users", 1) == 0 and isinstance(data, bpy.types.Mesh):
                        bpy.data.meshes.remove(data)
                bpy.data.collections.remove(child)

        bpy.ops.object.select_all(action="DESELECT")
        target = branch if branch and context.view_layer.objects.get(branch.name) else foliage
        if target:
            target.select_set(True)
            context.view_layer.objects.active = target
        elif previous_active and context.view_layer.objects.get(previous_active.name):
            previous_active.select_set(True)
            context.view_layer.objects.active = previous_active

        self.report({"INFO"}, "Foliage instances baked to real geometry")
        return {"FINISHED"}


CLASSES = (
    TREES2_OT_ApplyPreset,
    TREES2_OT_CreateTree,
    TREES2_OT_RegenerateTree,
    TREES2_OT_LoadTreeSettings,
    TREES2_OT_RandomizeSeed,
    TREES2_OT_GenerateLODSet,
    TREES2_OT_BakeFoliage,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
