import bpy


def _settings(context):
    return context.scene.trees2_settings


def _active_tree_root(context):
    obj = context.active_object
    if not obj:
        return None
    name = obj.get("trees2_root_collection")
    return bpy.data.collections.get(name) if name else None


class TREES2_PT_MainPanel(bpy.types.Panel):
    bl_label = "Trees 2.0"
    bl_idname = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Trees 2.0"

    def draw(self, context):
        layout = self.layout
        s = _settings(context)

        row = layout.row(align=True)
        row.prop(s, "species_preset", text="")
        row.operator("trees2.apply_preset", text="Apply")

        row = layout.row(align=True)
        row.prop(s, "seed")
        row.operator("trees2.randomize_seed", text="", icon="FILE_REFRESH")

        layout.operator("trees2.create_tree", icon="OUTLINER_OB_MESH")
        root = _active_tree_root(context)
        if root:
            row = layout.row(align=True)
            row.operator("trees2.regenerate_tree", icon="FILE_REFRESH")
            row.operator("trees2.load_tree_settings", text="Load Settings", icon="IMPORT")

            branch = context.active_object
            if branch and "trees2_branch_count" in branch:
                box = layout.box()
                box.label(text=f"Branches: {branch.get('trees2_branch_count', 0)}")
                box.label(text=f"Terminal branches: {branch.get('trees2_terminal_count', 0)}")
                box.label(text=f"Dead branches: {branch.get('trees2_dead_branches', 0)}")
                box.label(text=f"Foliage instances: {branch.get('trees2_leaf_points', 0)}")


class TREES2_PT_Structure(bpy.types.Panel):
    bl_label = "Trunk & Crown"
    bl_idname = "TREES2_PT_structure"
    bl_parent_id = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s = _settings(context)
        layout.prop(s, "height")
        layout.prop(s, "base_radius")
        layout.prop(s, "root_flare")
        layout.prop(s, "trunk_segments")
        layout.prop(s, "trunk_irregularity")
        layout.prop(s, "trunk_taper")
        layout.separator()
        layout.prop(s, "crown_shape")
        layout.prop(s, "branch_start")


class TREES2_PT_Branches(bpy.types.Panel):
    bl_label = "Branching"
    bl_idname = "TREES2_PT_branches"
    bl_parent_id = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s = _settings(context)
        layout.prop(s, "branch_distribution")
        layout.prop(s, "branch_levels")
        layout.prop(s, "primary_branches")
        if s.branch_levels > 1:
            layout.prop(s, "secondary_per_branch")
        layout.prop(s, "branch_angle")
        layout.prop(s, "azimuth_jitter")
        layout.prop(s, "branch_length")
        layout.prop(s, "branch_length_randomness")
        layout.prop(s, "branch_bend")
        layout.prop(s, "branch_droop")
        layout.prop(s, "apical_dominance")
        layout.prop(s, "phototropism")
        layout.prop(s, "branch_collar")
        layout.separator()
        layout.prop(s, "dead_branch_probability")
        layout.prop(s, "prune_probability")


class TREES2_PT_Foliage(bpy.types.Panel):
    bl_label = "2D Foliage Cards"
    bl_idname = "TREES2_PT_foliage"
    bl_parent_id = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s = _settings(context)
        layout.prop(s, "foliage_density")
        layout.prop(s, "foliage_start")
        layout.prop(s, "foliage_tip_bias")
        layout.prop(s, "foliage_spread")
        layout.prop(s, "leaf_up_bias")
        layout.separator()
        layout.prop(s, "card_style")
        layout.prop(s, "card_scale")
        layout.prop(s, "card_scale_randomness")
        layout.prop(s, "card_aspect")
        layout.prop(s, "card_bend")


class TREES2_PT_Materials(bpy.types.Panel):
    bl_label = "Textures & Atlas"
    bl_idname = "TREES2_PT_materials"
    bl_parent_id = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s = _settings(context)
        box = layout.box()
        box.label(text="Leaves", icon="IMAGE_DATA")
        box.prop(s, "leaf_image")
        box.prop(s, "leaf_normal_image")
        box.prop(s, "leaf_roughness_image")
        box.prop(s, "leaf_tint")
        row = box.row(align=True)
        row.prop(s, "atlas_columns")
        row.prop(s, "atlas_rows")
        max_cells = s.atlas_columns * s.atlas_rows
        box.prop(s, "atlas_variants")
        if s.atlas_variants > max_cells:
            box.label(text=f"Used Cells is clamped to {max_cells} at generation.", icon="INFO")

        box = layout.box()
        box.label(text="Bark", icon="MATERIAL")
        box.prop(s, "bark_image")
        box.prop(s, "bark_normal_image")
        box.prop(s, "bark_color")
        box.prop(s, "bark_uv_scale")


class TREES2_PT_Optimization(bpy.types.Panel):
    bl_label = "LOD, Wind & Export"
    bl_idname = "TREES2_PT_optimization"
    bl_parent_id = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s = _settings(context)
        layout.prop(s, "lod")
        layout.prop(s, "cap_branch_tips")
        layout.prop(s, "generate_wind_attributes")
        if s.generate_wind_attributes:
            layout.prop(s, "wind_height_power")
        layout.prop(s, "realize_foliage")
        layout.label(text="Keep foliage instanced while authoring.", icon="INFO")
        layout.operator("trees2.generate_lod_set", icon="MOD_ARRAY")
        layout.separator()
        layout.operator("trees2.bake_foliage", icon="CHECKMARK")
        layout.label(text="Bake only when preparing a mesh export.", icon="ERROR")


CLASSES = (
    TREES2_PT_MainPanel,
    TREES2_PT_Structure,
    TREES2_PT_Branches,
    TREES2_PT_Foliage,
    TREES2_PT_Materials,
    TREES2_PT_Optimization,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
