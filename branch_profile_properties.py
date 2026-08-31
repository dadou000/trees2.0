import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty


PROFILE_ITEMS = (
    ("AUTO", "Automatic by Species", "Choose a branch thickness profile from the active tree species preset"),
    ("BROADLEAF", "Broadleaf", "Balanced broadleaf profile with a long thick mid-section"),
    ("OAK", "Heavy / Oak", "Heavy limbs that retain thickness until late in the branch"),
    ("BIRCH", "Slender / Birch", "Lighter, slimmer branches with an earlier taper"),
    ("WILLOW", "Flexible / Willow", "Long slender branches with gradual flexible-looking taper"),
    ("CONIFER", "Conifer", "Moderately persistent thickness with lighter lateral branches"),
    ("CUSTOM", "Custom", "Use the manual profile values below"),
)


class TREES2_PG_BranchProfileSettings(bpy.types.PropertyGroup):
    enabled: BoolProperty(
        name="Realistic Branch Profiles",
        default=True,
        description="Replace cone-like branch taper with a thick mid-section, late distal taper, base swelling and stable radius variation",
    )
    profile_preset: EnumProperty(
        name="Profile",
        items=PROFILE_ITEMS,
        default="AUTO",
    )

    hold_thickness: FloatProperty(
        name="Hold Thickness",
        default=0.86,
        min=0.50,
        max=0.99,
        subtype="FACTOR",
        description="Fraction of base thickness retained before the final distal taper",
    )
    taper_start: FloatProperty(
        name="Taper Start",
        default=0.72,
        min=0.30,
        max=0.95,
        subtype="FACTOR",
        description="Fraction of branch length where the stronger tip taper begins",
    )
    tip_ratio: FloatProperty(
        name="Tip Thickness",
        default=0.05,
        min=0.008,
        max=0.22,
        subtype="FACTOR",
        description="Final tip radius as a fraction of branch base radius",
    )
    taper_curve: FloatProperty(
        name="Taper Curve",
        default=1.8,
        min=0.6,
        max=4.0,
        description="Higher values delay most radius loss until closer to the tip",
    )
    radius_variation: FloatProperty(
        name="Radius Variation",
        default=0.06,
        min=0.0,
        max=0.25,
        subtype="FACTOR",
        description="Low-frequency thickness variation and small natural branch swellings",
    )
    base_swell: FloatProperty(
        name="Base Swell",
        default=0.10,
        min=0.0,
        max=0.40,
        subtype="FACTOR",
        description="Extra proximal thickening near the branch attachment",
    )

    primary_radius_min: FloatProperty(
        name="Primary Min",
        default=0.58,
        min=0.20,
        max=0.90,
        subtype="FACTOR",
        description="Minimum primary branch base radius relative to the parent radius",
    )
    primary_radius_max: FloatProperty(
        name="Primary Max",
        default=0.76,
        min=0.25,
        max=0.96,
        subtype="FACTOR",
        description="Maximum primary branch base radius relative to the parent radius",
    )
    secondary_radius_min: FloatProperty(
        name="Secondary Min",
        default=0.44,
        min=0.15,
        max=0.80,
        subtype="FACTOR",
    )
    secondary_radius_max: FloatProperty(
        name="Secondary Max",
        default=0.60,
        min=0.20,
        max=0.88,
        subtype="FACTOR",
    )
    tertiary_radius_min: FloatProperty(
        name="Tertiary+ Min",
        default=0.36,
        min=0.10,
        max=0.70,
        subtype="FACTOR",
    )
    tertiary_radius_max: FloatProperty(
        name="Tertiary+ Max",
        default=0.52,
        min=0.15,
        max=0.78,
        subtype="FACTOR",
    )

    level_taper_shift: FloatProperty(
        name="Taper Shift / Level",
        default=0.035,
        min=0.0,
        max=0.12,
        subtype="FACTOR",
        description="Higher-order twigs begin their distal taper slightly earlier",
    )
    level_hold_loss: FloatProperty(
        name="Hold Loss / Level",
        default=0.025,
        min=0.0,
        max=0.10,
        subtype="FACTOR",
        description="Higher-order twigs retain slightly less of their base radius",
    )
    branch_variation: FloatProperty(
        name="Branch-to-Branch Variation",
        default=0.08,
        min=0.0,
        max=0.30,
        subtype="FACTOR",
        description="Stable variation in taper timing and thickness between individual branches",
    )


CLASSES = (TREES2_PG_BranchProfileSettings,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.trees2_branch_profile = PointerProperty(type=TREES2_PG_BranchProfileSettings)


def unregister():
    if hasattr(bpy.types.Scene, "trees2_branch_profile"):
        del bpy.types.Scene.trees2_branch_profile
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
