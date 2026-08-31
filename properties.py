import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
)


class TREES2_PG_Settings(bpy.types.PropertyGroup):
    seed: IntProperty(name="Seed", default=1, min=0, max=2_147_483_647)

    height: FloatProperty(name="Height", default=12.0, min=1.0, max=100.0, unit="LENGTH")
    base_radius: FloatProperty(name="Trunk Radius", default=0.45, min=0.03, max=5.0, unit="LENGTH")
    trunk_segments: IntProperty(name="Trunk Segments", default=18, min=4, max=96)
    trunk_irregularity: FloatProperty(name="Trunk Irregularity", default=0.12, min=0.0, max=1.0)
    trunk_taper: FloatProperty(name="Trunk Taper", default=0.92, min=0.5, max=0.995)

    branch_levels: IntProperty(name="Branch Levels", default=2, min=1, max=3)
    primary_branches: IntProperty(name="Primary Branches", default=18, min=2, max=80)
    secondary_per_branch: IntProperty(name="Children / Branch", default=3, min=0, max=8)
    branch_start: FloatProperty(name="Branch Start", default=0.24, min=0.05, max=0.8, subtype="FACTOR")
    branch_angle: FloatProperty(name="Branch Angle", default=1.05, min=0.15, max=1.5, subtype="ANGLE")
    branch_length: FloatProperty(name="Branch Length", default=4.4, min=0.2, max=30.0, unit="LENGTH")
    branch_length_randomness: FloatProperty(name="Length Randomness", default=0.35, min=0.0, max=0.9)
    branch_bend: FloatProperty(name="Branch Bend", default=0.18, min=0.0, max=1.0)
    branch_droop: FloatProperty(name="Droop", default=0.18, min=-0.5, max=1.5)

    foliage_density: FloatProperty(name="Foliage Density", default=1.0, min=0.0, max=4.0)
    foliage_start: FloatProperty(name="Foliage Start", default=0.52, min=0.0, max=0.95, subtype="FACTOR")
    card_scale: FloatProperty(name="Card Scale", default=0.72, min=0.05, max=5.0, unit="LENGTH")
    card_scale_randomness: FloatProperty(name="Scale Randomness", default=0.28, min=0.0, max=0.8)
    card_aspect: FloatProperty(name="Card Aspect", default=1.25, min=0.3, max=3.0)
    card_style: EnumProperty(
        name="Card Cluster",
        items=(
            ("SINGLE", "Single", "One quad per foliage point"),
            ("CROSS", "Crossed", "Two crossed quads per foliage point"),
            ("TRI", "Tri-Cross", "Three intersecting quads per foliage point"),
        ),
        default="CROSS",
    )
    leaf_image: PointerProperty(name="Leaf Atlas", type=bpy.types.Image)
    leaf_tint: FloatVectorProperty(
        name="Leaf Tint", subtype="COLOR", size=4,
        default=(0.12, 0.32, 0.055, 1.0), min=0.0, max=1.0,
    )
    bark_color: FloatVectorProperty(
        name="Bark Color", subtype="COLOR", size=4,
        default=(0.16, 0.07, 0.025, 1.0), min=0.0, max=1.0,
    )

    lod: EnumProperty(
        name="LOD",
        items=(
            ("LOD0", "LOD 0 - Hero", "Highest detail"),
            ("LOD1", "LOD 1 - Near", "Reduced branches and foliage"),
            ("LOD2", "LOD 2 - Mid", "Aggressive reduction"),
            ("LOD3", "LOD 3 - Far", "Very cheap canopy representation"),
        ),
        default="LOD0",
    )
    realize_foliage: BoolProperty(
        name="Realize Foliage", default=False,
        description="Convert foliage instances to real geometry inside the Geometry Nodes modifier",
    )


CLASSES = (TREES2_PG_Settings,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.trees2_settings = PointerProperty(type=TREES2_PG_Settings)


def unregister():
    del bpy.types.Scene.trees2_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
