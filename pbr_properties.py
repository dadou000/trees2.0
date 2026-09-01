import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import properties


class TREES2_PG_PBRSettings(bpy.types.PropertyGroup):
    output_directory: StringProperty(
        name="Output Directory",
        subtype="DIR_PATH",
        default="//trees2_generated_pbr/",
        description="Folder used for generated PNG texture sets",
    )
    leaf_resolution: IntProperty(
        name="Leaf Atlas Resolution", default=1024, min=128, max=4096,
        description="Total square resolution of the generated leaf atlas; high resolutions can take a long time",
    )
    leaf_quality: EnumProperty(
        name="Leaf Synthesis Quality",
        items=(
            ("HIGH", "High", "High-quality structural leaf synthesis at native atlas-cell resolution"),
            ("ULTRA", "Ultra", "2x per-cell supersampling for cleaner silhouettes, veins and normals; recommended default"),
            ("EXTREME", "Extreme", "3x per-cell supersampling for maximum edge and venation quality; very slow and memory intensive"),
        ),
        default="ULTRA",
        description="Quality of the high-fidelity species-aware leaf and needle texture synthesizer",
    )
    bark_resolution: IntProperty(
        name="Bark Resolution", default=1024, min=128, max=4096,
        description="Square resolution of each tileable bark texture; high resolutions can take a long time",
    )
    bark_quality: EnumProperty(
        name="Bark Synthesis Quality",
        items=(
            ("HIGH", "High", "High-quality multi-scale bark synthesis with a moderate structural working resolution"),
            ("ULTRA", "Ultra", "More structural detail, cellular breakup and noise octaves; recommended default"),
            ("EXTREME", "Extreme", "Maximum structural working resolution and octave count; can be very slow and memory intensive"),
        ),
        default="ULTRA",
        description="Quality of the high-fidelity species-aware trunk texture synthesizer",
    )
    atlas_grid: IntProperty(
        name="Leaf Atlas Grid", default=4, min=1, max=8,
        description="Number of atlas cells per axis; 4 creates 16 variants",
    )
    seed_offset: IntProperty(name="Texture Seed Offset", default=0, min=0, max=2_147_483_647)
    leaf_detail: FloatProperty(
        name="Leaf Detail", default=1.0, min=0.25, max=2.5,
        description="Multiplier for venation, serration, curvature, mottling and small leaf detail",
    )
    bark_detail: FloatProperty(
        name="Bark Detail", default=1.0, min=0.25, max=2.5,
        description="Multiplier for bark fissures, ridges, plates and fine breakup",
    )
    leaf_normal_strength: FloatProperty(name="Leaf Normal Strength", default=1.0, min=0.0, max=3.0)
    bark_normal_strength: FloatProperty(name="Bark Normal Strength", default=1.0, min=0.0, max=3.0)
    generate_leaves: BoolProperty(name="Generate Leaf / Needle Atlas", default=True)
    generate_bark: BoolProperty(name="Generate Bark PBR", default=True)
    auto_assign: BoolProperty(
        name="Assign Generated Maps", default=True,
        description="Assign generated images to the active Trees 2.0 settings and selected tree",
    )
    neutralize_tints: BoolProperty(
        name="Use Raw Generated Albedo Colors", default=False,
        description="Legacy mode: ignore the tree's chosen colors and use generated species albedo directly",
    )
    pack_images: BoolProperty(
        name="Pack Images in .blend", default=False,
        description="Also pack generated PNGs into the current Blender file",
    )


CLASSES = (TREES2_PG_PBRSettings,)
_DYNAMIC_TREE_PROPS = (
    "leaf_translucency_image",
    "bark_roughness_image",
    "bark_height_image",
    "bark_ao_image",
)


def register():
    # These live on the normal tree settings so they survive normal tree
    # creation/regeneration and can be consumed by the live material builder.
    properties.TREES2_PG_Settings.leaf_translucency_image = PointerProperty(
        name="Leaf Translucency", type=bpy.types.Image
    )
    properties.TREES2_PG_Settings.bark_roughness_image = PointerProperty(
        name="Bark Roughness", type=bpy.types.Image
    )
    properties.TREES2_PG_Settings.bark_height_image = PointerProperty(
        name="Bark Height", type=bpy.types.Image
    )
    properties.TREES2_PG_Settings.bark_ao_image = PointerProperty(
        name="Bark AO", type=bpy.types.Image
    )
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.trees2_pbr_settings = PointerProperty(type=TREES2_PG_PBRSettings)


def unregister():
    if hasattr(bpy.types.Scene, "trees2_pbr_settings"):
        del bpy.types.Scene.trees2_pbr_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    for name in _DYNAMIC_TREE_PROPS:
        if hasattr(properties.TREES2_PG_Settings, name):
            delattr(properties.TREES2_PG_Settings, name)
