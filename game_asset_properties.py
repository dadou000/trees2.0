import bpy
from bpy.props import BoolProperty, EnumProperty, PointerProperty, StringProperty


class TREES2_PG_GameAssetExport(bpy.types.PropertyGroup):
    output_root: StringProperty(
        name="Output Folder",
        subtype="DIR_PATH",
        default="//Trees2_GameAssets/",
        description="Root folder used for organized game-ready tree assets",
    )
    asset_name: StringProperty(
        name="Asset Name",
        default="",
        description="Optional stable asset name. Empty uses species + seed",
    )
    export_format: EnumProperty(
        name="Geometry Format",
        items=(
            ("GLB", "GLB", "Single binary glTF containing wood and foliage mesh nodes"),
            ("GLTF_SEPARATE", "glTF Separate", "JSON glTF plus separate binary/resource files"),
        ),
        default="GLB",
    )
    organize_by_species: BoolProperty(
        name="Species Folders",
        default=True,
        description="Create a species folder before the individual tree asset folder",
    )
    copy_source_textures: BoolProperty(
        name="Copy Source Textures",
        default=True,
        description="Copy externally saved images used by exported materials into the asset textures folder",
    )
    write_runtime_metadata: BoolProperty(
        name="Runtime Metadata",
        default=True,
        description="Write branch graph and compact foliage-to-branch binding sidecars for GPU animation",
    )


CLASSES = (TREES2_PG_GameAssetExport,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.trees2_game_asset = PointerProperty(type=TREES2_PG_GameAssetExport)


def unregister():
    if hasattr(bpy.types.Scene, "trees2_game_asset"):
        del bpy.types.Scene.trees2_game_asset
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
