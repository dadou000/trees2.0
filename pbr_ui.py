import bpy

from .pbr_profiles import species_profile
from .species_appearance import appearance_profile


class TREES2_PT_ProceduralPBR(bpy.types.Panel):
    bl_label = "Procedural PBR Textures"
    bl_idname = "TREES2_PT_procedural_pbr"
    bl_parent_id = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.trees2_settings
        pbr = context.scene.trees2_pbr_settings
        appearance = appearance_profile(settings.species_preset, species_profile(settings.species_preset))

        box = layout.box()
        box.label(text=f"Species: {settings.species_preset}", icon="MATERIAL")
        box.label(text=f"Foliage: {appearance.get('morphology_label', 'Species morphology')}", icon="OUTLINER_OB_CURVES")
        box.prop(pbr, "generate_leaves")
        box.prop(pbr, "generate_bark")
        box.prop(pbr, "output_directory")

        color = layout.box()
        color.label(text="Species Color Authority", icon="COLOR")
        color.prop(settings, "pbr_respect_tree_colors")
        color.prop(settings, "leaf_tint")
        color.prop(settings, "bark_color")
        if settings.pbr_respect_tree_colors:
            color.prop(settings, "pbr_species_color_influence")
            color.label(text="Shape/alpha stays species-correct; these colors stay dominant.", icon="CHECKMARK")
        else:
            color.alert = True
            color.label(text="Raw generated albedo colors are active.", icon="ERROR")

        if pbr.generate_leaves:
            leaf = layout.box()
            leaf.label(text="Leaf / Needle Atlas", icon="IMAGE_DATA")
            leaf.prop(pbr, "leaf_resolution")
            leaf.prop(pbr, "atlas_grid")
            leaf.label(text=f"Variants: {pbr.atlas_grid * pbr.atlas_grid}")
            leaf.prop(pbr, "leaf_detail")
            leaf.prop(pbr, "leaf_normal_strength")
            leaf.label(text=f"Morphology: {appearance.get('morphology_label', 'Species default')}")

        if pbr.generate_bark:
            bark = layout.box()
            bark.label(text="Tileable Bark", icon="TEXTURE")
            bark.prop(pbr, "bark_resolution")
            bark.prop(pbr, "bark_detail")
            bark.prop(pbr, "bark_normal_strength")
            bark.label(text="Outputs: Albedo, Normal, Roughness, Height, AO")

        options = layout.box()
        options.label(text="Output")
        options.prop(pbr, "seed_offset")
        options.prop(pbr, "auto_assign")
        if pbr.auto_assign:
            options.label(text="Generated maps are applied to the selected tree.", icon="CHECKMARK")
        options.prop(pbr, "pack_images")

        advanced = layout.box()
        advanced.label(text="Compatibility")
        advanced.prop(pbr, "neutralize_tints")
        if pbr.neutralize_tints:
            advanced.label(text="Disables Respect Tree Colors after generation.", icon="ERROR")

        layout.operator("trees2.generate_procedural_pbr", icon="NODE_MATERIAL")
        layout.operator("trees2.apply_current_pbr", icon="MATERIAL")
        layout.operator("trees2.open_pbr_folder", icon="FILE_FOLDER")
        layout.label(text="Generation writes exportable PNG files.", icon="INFO")


CLASSES = (TREES2_PT_ProceduralPBR,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
