bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 4, 0),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with species PBR synthesis, competition growth, realistic branch profiles, position-aware foliage, exact junctions, stable LODs, impostors, and GitHub update checks",
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
    foliage_sizing,
    foliage_sizing_properties,
    foliage_sizing_ui,
    operators,
    pbr_properties,
    pbr_ui,
    procedural_pbr,
    properties,
    ui,
    update_checker,
)


def register():
    properties.register()
    advanced_properties.register()
    branch_profile_properties.register()
    foliage_sizing_properties.register()
    pbr_properties.register()
    advanced_growth.install()
    # Radius profiles run after stochastic/competition growth so they can
    # reshape thickness without changing branch positions or RNG decisions.
    branch_profiles.install()
    # Position sizing runs after foliage placement and only changes card scale,
    # preserving the stable master population used by the LOD system.
    foliage_sizing.install()
    exact_junctions.install()
    # Patch Generate LOD Set before the original operator classes are registered.
    advanced_operators.register()
    operators.register()
    procedural_pbr.register()
    ui.register()
    advanced_ui.register()
    branch_profile_ui.register()
    foliage_sizing_ui.register()
    pbr_ui.register()
    update_checker.register()


def unregister():
    update_checker.unregister()
    pbr_ui.unregister()
    foliage_sizing_ui.unregister()
    branch_profile_ui.unregister()
    advanced_ui.unregister()
    ui.unregister()
    procedural_pbr.unregister()
    operators.unregister()
    advanced_operators.unregister()
    exact_junctions.uninstall()
    foliage_sizing.uninstall()
    branch_profiles.uninstall()
    advanced_growth.uninstall()
    pbr_properties.unregister()
    foliage_sizing_properties.unregister()
    branch_profile_properties.unregister()
    advanced_properties.unregister()
    properties.unregister()
