import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
)

from .presets import PRESET_ITEMS


class TREES2_PG_Settings(bpy.types.PropertyGroup):
    seed: IntProperty(name="Seed", default=1, min=0, max=2_147_483_647)
    species_preset: EnumProperty(
        name="Preset",
        items=PRESET_ITEMS,
        default="GENERIC",
    )

    height: FloatProperty(name="Height", default=12.0, min=1.0, max=100.0, unit="LENGTH")
    base_radius: FloatProperty(name="Trunk Radius", default=0.45, min=0.03, max=5.0, unit="LENGTH")
    trunk_segments: IntProperty(name="Trunk Segments", default=18, min=4, max=128)
    trunk_irregularity: FloatProperty(name="Trunk Irregularity", default=0.12, min=0.0, max=1.0)
    trunk_taper: FloatProperty(name="Trunk Taper", default=0.92, min=0.35, max=2.5)
    root_flare: FloatProperty(name="Root Flare", default=0.35, min=0.0, max=2.5)

    crown_shape: EnumProperty(
        name="Crown Shape",
        items=(
            ("ROUND", "Round", "Broad rounded crown"),
            ("OVAL", "Oval", "Vertically elongated crown"),
            ("COLUMNAR", "Columnar", "Narrow crown with nearly constant width"),
            ("CONICAL", "Conical", "Wide lower crown tapering toward the apex"),
            ("VASE", "Vase", "Crown widens toward the upper half"),
            ("UMBRELLA", "Umbrella", "Flat broad upper crown"),
        ),
        default="ROUND",
    )
    branch_distribution: EnumProperty(
        name="Distribution",
        items=(
            ("PHYLLOTAXIS", "Phyllotaxis", "Golden-angle spiral distribution"),
            ("RANDOM", "Random", "Random branch azimuth"),
            ("WHORLED", "Whorled", "Branches grouped in loose whorls"),
        ),
        default="PHYLLOTAXIS",
    )
    branch_levels: IntProperty(name="Branch Levels", default=3, min=1, max=4)
    primary_branches: IntProperty(name="Primary Branches", default=20, min=2, max=120)
    secondary_per_branch: IntProperty(name="Children / Branch", default=3, min=0, max=12)
    branch_start: FloatProperty(name="Crown Start", default=0.24, min=0.03, max=0.85, subtype="FACTOR")
    branch_angle: FloatProperty(name="Branch Angle", default=1.02, min=0.08, max=1.55, subtype="ANGLE")
    azimuth_jitter: FloatProperty(name="Azimuth Jitter", default=0.22, min=0.0, max=1.5, subtype="ANGLE")
    branch_length: FloatProperty(name="Max Branch Length", default=4.4, min=0.2, max=40.0, unit="LENGTH")
    branch_length_randomness: FloatProperty(name="Length Randomness", default=0.28, min=0.0, max=0.95)
    branch_bend: FloatProperty(name="Branch Bend", default=0.16, min=0.0, max=1.5)
    branch_droop: FloatProperty(name="Droop", default=0.16, min=-0.75, max=2.5)
    apical_dominance: FloatProperty(name="Apical Dominance", default=0.42, min=0.0, max=1.0)
    phototropism: FloatProperty(name="Upward Growth", default=0.18, min=-0.5, max=1.0)
    branch_collar: FloatProperty(name="Branch Collar", default=0.32, min=0.0, max=1.5)
    dead_branch_probability: FloatProperty(name="Dead Branch Chance", default=0.02, min=0.0, max=0.8, subtype="FACTOR")
    prune_probability: FloatProperty(name="Natural Pruning", default=0.035, min=0.0, max=0.8, subtype="FACTOR")

    foliage_density: FloatProperty(name="Foliage Density", default=1.0, min=0.0, max=6.0)
    foliage_start: FloatProperty(name="Foliage Start", default=0.48, min=0.0, max=0.98, subtype="FACTOR")
    foliage_tip_bias: FloatProperty(name="Tip Bias", default=0.65, min=0.0, max=1.0, subtype="FACTOR")
    foliage_spread: FloatProperty(name="Cluster Spread", default=0.55, min=0.0, max=2.0)
    leaf_up_bias: FloatProperty(name="Up Bias", default=0.55, min=0.0, max=1.0, subtype="FACTOR")
    card_scale: FloatProperty(name="Card Scale", default=0.72, min=0.03, max=8.0, unit="LENGTH")
    card_scale_randomness: FloatProperty(name="Scale Randomness", default=0.26, min=0.0, max=0.9)
    card_aspect: FloatProperty(name="Card Aspect", default=1.25, min=0.25, max=4.0)
    card_bend: FloatProperty(name="Card Bend", default=0.08, min=0.0, max=0.5)
    card_style: EnumProperty(
        name="Card Cluster",
        items=(
            ("SINGLE", "Single", "One bent card per foliage point"),
            ("CROSS", "Crossed", "Two intersecting bent cards"),
            ("TRI", "Tri-Cross", "Three intersecting bent cards"),
        ),
        default="CROSS",
    )

    leaf_image: PointerProperty(name="Leaf Atlas", type=bpy.types.Image)
    leaf_normal_image: PointerProperty(name="Leaf Normal", type=bpy.types.Image)
    leaf_roughness_image: PointerProperty(name="Leaf Roughness", type=bpy.types.Image)
    atlas_columns: IntProperty(name="Atlas Columns", default=1, min=1, max=16)
    atlas_rows: IntProperty(name="Atlas Rows", default=1, min=1, max=16)
    atlas_variants: IntProperty(name="Used Cells", default=1, min=1, max=256)
    leaf_tint: FloatVectorProperty(
        name="Foliage Color", subtype="COLOR", size=4,
        default=(0.12, 0.32, 0.055, 1.0), min=0.0, max=1.0,
        description="Final foliage color; procedural atlases preserve this hue while adding species detail",
    )

    bark_image: PointerProperty(name="Bark Color", type=bpy.types.Image)
    bark_normal_image: PointerProperty(name="Bark Normal", type=bpy.types.Image)
    bark_color: FloatVectorProperty(
        name="Trunk Color", subtype="COLOR", size=4,
        default=(0.16, 0.07, 0.025, 1.0), min=0.0, max=1.0,
        description="Final trunk/bark color; procedural bark preserves this hue while adding detail",
    )
    bark_uv_scale: FloatProperty(name="Bark UV Scale", default=1.0, min=0.05, max=20.0)

    pbr_respect_tree_colors: BoolProperty(
        name="Respect Tree Colors",
        default=True,
        description="Keep Foliage Color and Trunk Color authoritative while using generated albedo for texture detail",
    )
    pbr_species_color_influence: FloatProperty(
        name="Species Hue Influence",
        default=0.10,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
        description="Amount of generated species hue blended back into the authoritative tree colors",
    )

    generate_wind_attributes: BoolProperty(
        name="Wind Attributes", default=True,
        description="Write trees2_wind_weight, trees2_wind_phase and trees2_stiffness attributes",
    )
    wind_height_power: FloatProperty(name="Wind Height Curve", default=1.45, min=0.25, max=4.0)
    lod: EnumProperty(
        name="LOD",
        items=(
            ("LOD0", "LOD 0 - Hero", "Highest branch and foliage detail"),
            ("LOD1", "LOD 1 - Near", "Reduced radial segments and foliage"),
            ("LOD2", "LOD 2 - Mid", "Aggressive branch reduction"),
            ("LOD3", "LOD 3 - Far", "Very cheap card-based canopy"),
            ("LOD4", "LOD 4 - Proxy", "Ultra-cheap billboard-like proxy tree"),
        ),
        default="LOD0",
    )
    realize_foliage: BoolProperty(
        name="Realize Foliage", default=False,
        description="Convert foliage instances to real geometry inside the Geometry Nodes modifier",
    )
    cap_branch_tips: BoolProperty(name="Cap Branch Tips", default=True)


CLASSES = (TREES2_PG_Settings,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.trees2_settings = PointerProperty(type=TREES2_PG_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "trees2_settings"):
        del bpy.types.Scene.trees2_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
