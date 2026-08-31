import bpy


class TREES2_PT_MainPanel(bpy.types.Panel):
    bl_label = "Trees 2.0"
    bl_idname = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Trees 2.0"

    def draw(self, context):
        layout = self.layout
        s = context.scene.trees2_settings

        row = layout.row(align=True)
        row.prop(s, "seed")
        row.operator("trees2.randomize_seed", text="", icon="FILE_REFRESH")

        box = layout.box()
        box.label(text="Structure", icon="OUTLINER_OB_CURVES")
        box.prop(s, "height")
        box.prop(s, "base_radius")
        box.prop(s, "trunk_segments")
        box.prop(s, "trunk_irregularity")
        box.prop(s, "trunk_taper")

        box = layout.box()
        box.label(text="Branches", icon="NODETREE")
        box.prop(s, "branch_levels")
        box.prop(s, "primary_branches")
        if s.branch_levels > 1:
            box.prop(s, "secondary_per_branch")
        box.prop(s, "branch_start")
        box.prop(s, "branch_angle")
        box.prop(s, "branch_length")
        box.prop(s, "branch_length_randomness")
        box.prop(s, "branch_bend")
        box.prop(s, "branch_droop")

        box = layout.box()
        box.label(text="2D Foliage Cards", icon="IMAGE_DATA")
        box.prop(s, "leaf_image")
        box.prop(s, "leaf_tint")
        box.prop(s, "foliage_density")
        box.prop(s, "foliage_start")
        box.prop(s, "card_style")
        box.prop(s, "card_scale")
        box.prop(s, "card_scale_randomness")
        box.prop(s, "card_aspect")

        box = layout.box()
        box.label(text="Game Optimization", icon="MOD_DECIM")
        box.prop(s, "lod")
        box.prop(s, "realize_foliage")
        box.label(text="Keep foliage unrealized for the lightest Blender scene.", icon="INFO")

        layout.prop(s, "bark_color")
        layout.separator()
        layout.operator("trees2.create_tree", icon="OUTLINER_OB_MESH")
        layout.operator("trees2.regenerate_tree", icon="FILE_REFRESH")
        layout.operator("trees2.generate_lod_set", icon="MOD_ARRAY")


CLASSES = (TREES2_PT_MainPanel,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
