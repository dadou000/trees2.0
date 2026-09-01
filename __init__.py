bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 7, 1),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with high-fidelity species leaf and bark synthesis, dedicated riven willow bark, smart foliage assembly, stable LODs, impostors, and GitHub updates",
    "category": "Add Mesh",
}

from . import (
    advanced_growth,
    advanced_operators,
    advanced_properties,
    advanced_ui,
    appearance_state,
    bark_synthesis,
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
    leaf_synthesis,
    leaf_synthesis_runtime,
    operators,
    pbr_live_apply,
    pbr_properties,
    pbr_ui,
    procedural_pbr,
    properties,
    ui,
    update_checker,
    willow_bark_synthesis,
    willow_foliage_fix,
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
    branch_profiles.install()
    foliage_assembly.install()
    foliage_assembly_lods.install()
    foliage_atlas_assembly.install()
    willow_foliage_fix.install()
    foliage_sizing.install()
    exact_junctions.install()
    advanced_operators.register()
    operators.register()
    procedural_pbr.register()
    bark_synthesis.install()
    # Mature weeping-willow bark has a dedicated riven/fibrous solve.  Install
    # after the general HQ bark generator so all non-willow species retain the
    # normal bark path while WILLOW gets the specialized structural generator.
    willow_bark_synthesis.install()
    leaf_synthesis.install()
    # Runtime integration assigns the generated translucency map, fixes atlas
    # surface compositing and exposes conservative thin-leaf scattering to the
    # material builder. Install before live-apply wraps PBR generation.
    leaf_synthesis_runtime.install()
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
    leaf_synthesis_runtime.uninstall()
    leaf_synthesis.uninstall()
    willow_bark_synthesis.uninstall()
    bark_synthesis.uninstall()
    procedural_pbr.unregister()
    operators.unregister()
    advanced_operators.unregister()
    exact_junctions.uninstall()
    foliage_sizing.uninstall()
    willow_foliage_fix.uninstall()
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
