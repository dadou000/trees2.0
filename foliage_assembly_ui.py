import bpy

from .foliage_assembly import effective_profile, resolved_mode


class TREES2_PT_FoliageAssembly(bpy.types.Panel):
    bl_label = "Smart Foliage Assembly"
    bl_idname = "TREES2_PT_foliage_assembly"
    bl_parent_id = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.trees2_foliage_assembly, "enabled", text="")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.trees2_settings
        assembly = context.scene.trees2_foliage_assembly
        layout.active = assembly.enabled

        profile = effective_profile(settings, assembly)
        box = layout.box()
        box.prop(assembly, "mode")
        box.label(text=f"Resolved: {resolved_mode(settings, assembly).replace('_', ' ').title()}")
        if resolved_mode(settings, assembly) == "WEEPING":
            box.label(text="Gravity-driven pendulous curtain assembly", icon="FORCE_FORCE")
        elif resolved_mode(settings, assembly) in {"CONIFER", "COLUMNAR"}:
            box.label(text="Twig-aligned needle / scale sprays", icon="OUTLINER_OB_CURVES")
        else:
            box.label(text="Parent-aligned batched leaf clusters", icon="OUTLINER_OB_POINTCLOUD")

        budget = layout.box()
        budget.label(text="Efficiency / Distribution")
        budget.prop(assembly, "density_budget")
        budget.prop(assembly, "spacing")
        budget.prop(assembly, "force_single_sources")
        budget.prop(assembly, "generated_atlas_aspect")
        budget.label(text="Single-card sources avoid coincident Cross/Tri slabs.", icon="INFO")

        orient = layout.box()
        orient.label(text="Orientation")
        orient.prop(assembly, "twig_alignment")
        orient.prop(assembly, "outward_bias")
        orient.prop(assembly, "gravity_response")
        orient.prop(assembly, "angular_jitter")

        if profile["mode"] == "WEEPING":
            willow = layout.box()
            willow.label(text="Weeping Curtains")
            willow.prop(assembly, "willow_length")
            willow.prop(assembly, "willow_ground_reach")
            willow.prop(assembly, "willow_spacing")
            willow.prop(assembly, "willow_flutter")
            willow.prop(assembly, "willow_max_cards")
            willow.label(text="Strands transition from twig direction toward gravity.")

        debug = layout.box()
        debug.label(text="Export")
        debug.prop(assembly, "write_debug_attributes")
        debug.label(text="LOD sets still derive from one deterministic master population.")


CLASSES = (TREES2_PT_FoliageAssembly,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
