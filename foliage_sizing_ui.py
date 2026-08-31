import bpy

from . import foliage_sizing


class TREES2_PT_FoliageSizing(bpy.types.Panel):
    bl_label = "Position-Aware Leaf Size"
    bl_idname = "TREES2_PT_foliage_sizing"
    bl_parent_id = "TREES2_PT_foliage"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.trees2_settings
        sizing = context.scene.trees2_foliage_sizing

        layout.prop(sizing, "enabled")
        column = layout.column()
        column.active = sizing.enabled
        column.prop(sizing, "sizing_mode")
        column.prop(sizing, "strength")

        if sizing.sizing_mode == "AUTO":
            values = foliage_sizing.effective_values(settings, sizing)
            box = column.box()
            box.label(text=f"Resolved profile: {values['resolved_name'].title()}")
            box.label(text="Interior/shade cards grow larger.")
            box.label(text="Exposed edge/top cards become smaller.")
        elif sizing.sizing_mode != "CUSTOM":
            box = column.box()
            values = foliage_sizing.effective_values(settings, sizing)
            box.label(text=f"Interior: {values['interior_scale']:.2f}x")
            box.label(text=f"Silhouette: {values['silhouette_scale']:.2f}x")
            box.label(text=f"Upper crown: {values['upper_crown_scale']:.2f}x")

        if sizing.sizing_mode == "CUSTOM":
            column.separator()
            column.label(text="Size Multipliers")
            column.prop(sizing, "interior_scale")
            column.prop(sizing, "silhouette_scale")
            column.prop(sizing, "upper_crown_scale")

            column.separator()
            column.label(text="Canopy Position")
            column.prop(sizing, "edge_start")
            column.prop(sizing, "top_start")
            column.prop(sizing, "radial_influence")
            column.prop(sizing, "vertical_influence")
            column.prop(sizing, "crown_width_multiplier")

            column.separator()
            column.label(text="Safety Limits")
            row = column.row(align=True)
            row.prop(sizing, "min_multiplier")
            row.prop(sizing, "max_multiplier")

        column.separator()
        column.label(text="Base Card Scale remains the global size.", icon="INFO")
        column.label(text="These values multiply it by canopy position.")


CLASSES = (TREES2_PT_FoliageSizing,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
