bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 5, 0),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with species-aware smart foliage assembly, species-correct PBR, competition growth, realistic branch profiles, stable LODs, impostors, and one-click GitHub updates",
    "category": "Add Mesh",
}

from . import (
    advanced_growth,
    advanced_operators,
    advanced_properties,
    advanced_ui,
    appearance_state,
    branch_profile_properties,
    branch_profile_ui,
    branch_profiles,
    exact_junctions,
    foliage_assembly,
    foliage_assembly_lods,
    foliage_assembly_properties,
    foliage_assembly_ui,
    foliage_atlas_assembly,
    foliage_sizing,
    foliage_sizing_properties,
    foliage_sizing_ui,
    operators,
    pbr_live_apply,
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
    foliage_assembly_properties.register()
    foliage_sizing_properties.register()
    pbr_properties.register()
    appearance_state.install()
    advanced_growth.install()
    # Radius profiles run after stochastic/competition growth so they can
    # reshape thickness without changing branch positions or RNG decisions.
    branch_profiles.install()
    # Smart assembly replaces coincident Cross/Tri bundles with deterministic
    # parent-aligned single-card instances and species-specific assembly modes.
    # It must install before position sizing so sizing wraps the smart records.
    foliage_assembly.install()
    foliage_assembly_lods.install()
    foliage_atlas_assembly.install()
    # Position sizing runs after foliage placement and only changes card scale,
    # preserving the stable master population used by the LOD system.
    foliage_sizing.install()
    exact_junctions.install()
    # Patch Generate LOD Set before the original operator classes are registered.
    advanced_operators.register()
    operators.register()
    procedural_pbr.register()
    # Wrap PBR generation after its operators exist so generated maps are also
    # pushed into the currently selected tree and its hidden card sources.
    pbr_live_apply.install()
    ui.register()
    advanced_ui.register()
    branch_profile_ui.register()
    foliage_assembly_ui.register()
    foliage_sizing_ui.register()
    pbr_ui.register()
    update_checker.register()


def unregister():
    update_checker.unregister()
    pbr_ui.unregister()
    foliage_sizing_ui.unregister()
    foliage_assembly_ui.unregister()
    branch_profile_ui.unregister()
    advanced_ui.unregister()
    ui.unregister()
    pbr_live_apply.uninstall()
    procedural_pbr.unregister()
    operators.unregister()
    advanced_operators.unregister()
    exact_junctions.uninstall()
    foliage_sizing.uninstall()
    foliage_atlas_assembly.uninstall()
    foliage_assembly_lods.uninstall()
    foliage_assembly.uninstall()
    branch_profiles.uninstall()
    advanced_growth.uninstall()
    appearance_state.uninstall()
    pbr_properties.unregister()
    foliage_sizing_properties.unregister()
    foliage_assembly_properties.unregister()
    branch_profile_properties.unregister()
    advanced_properties.unregister()
    properties.unregister()
