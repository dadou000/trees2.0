bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 3, 3),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with competition growth, realistic branch profiles, exact junctions, instanced foliage, and impostor LODs",
    "category": "Add Mesh",
}

from . import (
    advanced_growth,
    advanced_operators,
    advanced_properties,
    advanced_ui,
    branch_profile_properties,
    branch_profile_ui,
    branch_profiles,
    exact_junctions,
    operators,
    properties,
    ui,
)


def register():
    properties.register()
    advanced_properties.register()
    branch_profile_properties.register()
    advanced_growth.install()
    # Radius profiles run after stochastic/competition growth so they can
    # reshape thickness without changing branch positions or RNG decisions.
    branch_profiles.install()
    exact_junctions.install()
    # Patch Generate LOD Set before the original operator classes are registered.
    advanced_operators.register()
    operators.register()
    ui.register()
    advanced_ui.register()
    branch_profile_ui.register()


def unregister():
    branch_profile_ui.unregister()
    advanced_ui.unregister()
    ui.unregister()
    operators.unregister()
    advanced_operators.unregister()
    exact_junctions.uninstall()
    branch_profiles.uninstall()
    advanced_growth.uninstall()
    branch_profile_properties.unregister()
    advanced_properties.unregister()
    properties.unregister()
