import bpy


class TREES2_PT_Competition(bpy.types.Panel):
    bl_label = "Competition Growth"
    bl_idname = "TREES2_PT_competition"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Trees 2.0"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        a = context.scene.trees2_advanced_settings
        layout.prop(a, "use_space_colonization")
        body = layout.column()
        body.enabled = a.use_space_colonization
        body.prop(a, "attraction_points")
        body.prop(a, "attraction_influence")
        body.prop(a, "attraction_kill_distance")
        body.prop(a, "competition_clearance")
        body.prop(a, "attraction_strength")
        body.prop(a, "avoidance_strength")
        body.prop(a, "competition_lod_max")
        body.label(text="Attractors are consumed as branch space fills.", icon="INFO")


class TREES2_PT_Junctions(bpy.types.Panel):
    bl_label = "Branch Junctions"
    bl_idname = "TREES2_PT_junctions"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Trees 2.0"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        a = context.scene.trees2_advanced_settings
        layout.prop(a, "junction_mode")
        if a.junction_mode == "VOXEL_FUSE":
            layout.prop(a, "junction_voxel_size")
            layout.prop(a, "junction_adaptivity")
            layout.prop(a, "junction_fuse_lod_max")
            layout.prop(a, "reproject_branch_attributes")
            layout.label(text="Fused mode outputs one manifold woody volume.", icon="INFO")
            layout.label(text="Smaller voxels preserve thinner twigs but cost more.")


class TREES2_PT_Impostor(bpy.types.Panel):
    bl_label = "Automatic Impostor LOD"
    bl_idname = "TREES2_PT_impostor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Trees 2.0"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        a = context.scene.trees2_advanced_settings
        layout.prop(a, "impostor_views")
        layout.prop(a, "impostor_resolution")
        layout.prop(a, "impostor_elevation")
        layout.prop(a, "impostor_padding")
        layout.prop(a, "impostor_output_dir")
        layout.prop(a, "create_impostor_mesh")
        layout.prop(a, "replace_lod4_with_impostor")
        layout.operator("trees2.bake_impostor", icon="RENDER_STILL")
        layout.label(text="LOD mesh cost: 2 triangles per baked view.", icon="INFO")
        layout.label(text="Atlas uses RGBA with a transparent background.")


CLASSES = (TREES2_PT_Competition, TREES2_PT_Junctions, TREES2_PT_Impostor)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
