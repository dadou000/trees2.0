bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 8, 8),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with low multi-leader willow forks, hierarchy-aware structural motion, radial curtain canopies, direct PBR export, stable LODs, impostors, and GitHub updates",
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
    pbr_pipeline,
    pbr_properties,
    pbr_ui,
    procedural_pbr,
    properties,
    ui,
    update_checker,
    willow_anchor_distribution,
    willow_architecture,
    willow_bark_synthesis,
    willow_canopy_tuning,
    willow_crown_spread,
    willow_foliage_fix,
    willow_fork_dominance,
    willow_leaf_synthesis,
    willow_structure_motion,
    willow_tuning,
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

    # 1) Add sparse real mature-willow topology before deformation.
    willow_architecture.install()

    # 2) Break the remaining single-pole silhouette: add extra heavy leaders in
    # empty sectors and subordinate the original upper trunk above the fork zone.
    willow_fork_dominance.install()

    # 3) Bend the complete hierarchy while preserving child attachment frames.
    willow_structure_motion.install()

    # 4) Expand complete primary subtrees horizontally. Descendants receive the
    # same transform as their parent, so the broader dome keeps junctions.
    willow_crown_spread.install()

    # 5) Re-score virtual foliage supports on the final curved/spread skeleton.
    willow_anchor_distribution.install()

    foliage_assembly.install()
    foliage_assembly_lods.install()
    foliage_atlas_assembly.install()
    willow_foliage_fix.install()

    # 6) Shape whole willow curtains radially/vertically after continuous card
    # placement rather than deleting individual cards.
    willow_canopy_tuning.install()

    foliage_sizing.install()
    exact_junctions.install()
    advanced_operators.register()
    operators.register()
    procedural_pbr.register()

    # All generated texture files go through one direct PNG pipeline. Non-color
    # maps are written as 16-bit RGBA before Blender loads them.
    pbr_pipeline.install()

    bark_synthesis.install()
    willow_bark_synthesis.install()
    leaf_synthesis.install()
    leaf_synthesis_runtime.install()
    willow_leaf_synthesis.install()

    # Final willow defaults are target-driven and include the darker palette.
    willow_tuning.install()
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
    willow_tuning.uninstall()
    willow_leaf_synthesis.uninstall()
    leaf_synthesis_runtime.uninstall()
    leaf_synthesis.uninstall()
    willow_bark_synthesis.uninstall()
    bark_synthesis.uninstall()
    pbr_pipeline.uninstall()
    procedural_pbr.unregister()
    operators.unregister()
    advanced_operators.unregister()
    exact_junctions.uninstall()
    foliage_sizing.uninstall()
    willow_canopy_tuning.uninstall()
    willow_foliage_fix.uninstall()
    foliage_atlas_assembly.uninstall()
    foliage_assembly_lods.uninstall()
    foliage_assembly.uninstall()
    willow_anchor_distribution.uninstall()
    willow_crown_spread.uninstall()
    willow_structure_motion.uninstall()
    willow_fork_dominance.uninstall()
    willow_architecture.uninstall()
    branch_profiles.uninstall()
    advanced_growth.uninstall()
    appearance_state.uninstall()
    pbr_properties.unregister()
    foliage_sizing_properties.unregister()
    foliage_assembly_properties.unregister()
    branch_profile_properties.unregister()
    advanced_properties.unregister()
    properties.unregister()
