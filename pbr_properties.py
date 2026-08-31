import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import properties


class TREES2_PG_PBRSettings(bpy.types.PropertyGroup):
    output_directory: StringProperty(
        name="Output Directory",
        subtype="DIR_PATH",
        default="//trees2_generated_pbr/",
        description="Folder used for generated PNG texture sets",
    )
    leaf_resolution: IntProperty(
        name="Leaf Atlas Resolution", default=512, min=128, max=2048,
        description="Total square resolution of the generated leaf atlas",
    )
    bark_resolution: IntProperty(
        name="Bark Resolution", default=512, min=128, max=2048,
        description="Square resolution of each tileable bark texture",
    )
    atlas_grid: IntProperty(
        name="Leaf Atlas Grid", default=4, min=1, max=8,
        description="Number of atlas cells per axis; 4 creates 16 variants",
    )
    seed_offset: IntProperty(name="Texture Seed Offset", default=0, min=0, max=2_147_483_647)
    leaf_detail: FloatProperty(
        name="Leaf Detail", default=1.0, min=0.25, max=2.5,
        description="Multiplier for veins, serration and small leaf detail",
    )
    bark_detail: FloatProperty(
        name="Bark Detail", default=1.0, min=0.25, max=2.5,
        description="Multiplier for bark fissures and fine breakup",
    )
    leaf_normal_strength: FloatProperty(name="Leaf Normal Strength", default=1.0, min=0.0, max=3.0)
    bark_normal_strength: FloatProperty(name="Bark Normal Strength", default=1.0, min=0.0, max=3.0)
    generate_leaves: BoolProperty(name="Generate Leaf / Needle Atlas", default=True)
    generate_bark: BoolProperty(name="Generate Bark PBR", default=True)
    auto_assign: BoolProperty(
        name="Assign Generated Maps", default=True,
        description="Assign generated images to the active Trees 2.0 settings",
    )
    neutralize_tints: BoolProperty(
        name="Use Generated Albedo Colors", default=True,
        description="Set leaf and bark tint multipliers to white after assigning generated albedo",
    )
    pack_images: BoolProperty(
        name="Pack Images in .blend", default=False,
        description="Also pack generated PNGs into the current Blender file",
    )


CLASSES = (TREES2_PG_PBRSettings,)
_DYNAMIC_TREE_PROPS = (
    "bark_roughness_image",
    "bark_height_image",
    "bark_ao_image",
)


def register():
    # These live on the normal tree settings so they survive the usual
    # generation/regeneration flow just like bark_image and bark_normal_image.
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
