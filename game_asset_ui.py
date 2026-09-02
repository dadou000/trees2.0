import bpy


class TREES2_PT_GameAssetExport(bpy.types.Panel):
    bl_label = "Game Asset Export"
    bl_idname = "TREES2_PT_game_asset_export"
    bl_parent_id = "TREES2_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.trees2_game_asset

        layout.prop(settings, "output_root")
        layout.prop(settings, "asset_name")
        layout.prop(settings, "export_format")
        layout.prop(settings, "organize_by_species")
        layout.prop(settings, "copy_source_textures")
        layout.prop(settings, "write_runtime_metadata")

        box = layout.box()
        box.label(text="Output layout", icon="FILE_FOLDER")
        box.label(text="<root>/<species>/<asset>/manifest.json")
        box.label(text="geometry/LOD*/ + runtime/LOD* + textures/")

        layout.operator("trees2.export_game_asset", icon="EXPORT")
        layout.label(text="Exports wood + foliage as two mesh nodes.", icon="INFO")
        layout.label(text="Regenerate old trees once to add runtime mapping.", icon="INFO")


CLASSES = (TREES2_PT_GameAssetExport,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
