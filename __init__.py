bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 3, 0),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with competition growth, fused branches, instanced foliage, and impostor LODs",
    "category": "Add Mesh",
}

from . import (
    advanced_growth,
    advanced_operators,
    advanced_properties,
    advanced_ui,
    operators,
    properties,
    ui,
)


def register():
    properties.register()
    advanced_properties.register()
    advanced_growth.install()
    operators.register()
    advanced_operators.register()
    ui.register()
    advanced_ui.register()


def unregister():
    advanced_ui.unregister()
    ui.unregister()
    advanced_operators.unregister()
    operators.unregister()
    advanced_growth.uninstall()
    advanced_properties.unregister()
    properties.unregister()
