import bpy

from .branch_profiles import effective_profile


class TREES2_PT_BranchProfile(bpy.types.Panel):
    bl_label = "Branch Profile"
    bl_idname = "TREES2_PT_branch_profile"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Trees 2.0"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        profile = context.scene.trees2_branch_profile
        settings = context.scene.trees2_settings

        layout.prop(profile, "enabled")
        body = layout.column()
        body.enabled = profile.enabled
        body.prop(profile, "profile_preset")

        if profile.profile_preset == "AUTO":
            resolved = effective_profile(settings, profile)["resolved_name"]
            body.label(text=f"Resolved profile: {resolved.title()}", icon="INFO")

        if profile.profile_preset == "CUSTOM":
            shape = body.box()
            shape.label(text="Longitudinal Radius Profile")
            shape.prop(profile, "hold_thickness")
            shape.prop(profile, "taper_start")
            shape.prop(profile, "tip_ratio")
            shape.prop(profile, "taper_curve")
            shape.prop(profile, "radius_variation")
            shape.prop(profile, "base_swell")

            thickness = body.box()
            thickness.label(text="Child / Parent Radius")
            row = thickness.row(align=True)
            row.prop(profile, "primary_radius_min")
            row.prop(profile, "primary_radius_max")
            row = thickness.row(align=True)
            row.prop(profile, "secondary_radius_min")
            row.prop(profile, "secondary_radius_max")
            row = thickness.row(align=True)
            row.prop(profile, "tertiary_radius_min")
            row.prop(profile, "tertiary_radius_max")

            variation = body.box()
            variation.label(text="Hierarchy Variation")
            variation.prop(profile, "level_taper_shift")
            variation.prop(profile, "level_hold_loss")
            variation.prop(profile, "branch_variation")
        else:
            values = effective_profile(settings, profile)
            box = body.box()
            box.label(text="Effective Profile")
            box.label(text=f"Hold thickness: {values['hold_thickness']:.2f}")
            box.label(text=f"Strong taper begins: {values['taper_start']:.2f} of length")
            box.label(text=f"Tip thickness: {values['tip_ratio']:.3f}")
            box.label(text=f"Radius variation: {values['radius_variation']:.3f}")
            box.label(text=f"Primary ratio: {values['primary'][0]:.2f} - {values['primary'][1]:.2f}")
            box.label(text=f"Secondary ratio: {values['secondary'][0]:.2f} - {values['secondary'][1]:.2f}")

        body.label(text="Profiles are deterministic and shared by every LOD.", icon="INFO")
        body.label(text="Trunk shape is unchanged; this controls child branches.")


CLASSES = (TREES2_PT_BranchProfile,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
