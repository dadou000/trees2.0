bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 2, 1),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees using low-poly branches and instanced 2D foliage cards",
    "category": "Add Mesh",
}

from . import operators, properties, ui


def register():
    properties.register()
    operators.register()
    ui.register()


def unregister():
    ui.unregister()
    operators.unregister()
    properties.unregister()
