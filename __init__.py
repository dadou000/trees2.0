bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 9, 0),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with research-based sympodial willow relay growth, hierarchy-aware structural motion, dense curtain canopies, direct PBR export, stable LODs, impostors, and GitHub updates",
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
    willow_crown_spread,
    willow_foliage_fix,
    willow_leaf_synthesis,
    willow_relay_architecture,
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

    # Willow 0.9: research-based sympodial architecture.  Suppress the older
    # artificial equal co-dominant leaders, retain roots/scaffold augmentation,
    # then physically terminate the basal trunk and continue height through
    # successive vigorous relay axes.
    willow_relay_architecture.prepare()
    willow_architecture.install()
    willow_relay_architecture.install()

    # Bend the complete relay hierarchy while preserving child attachment frames.
    willow_structure_motion.install()

    # Give the resulting scaffold/relay subtrees a modest broad-crown correction.
    willow_crown_spread.install()

    # Re-score cheap virtual foliage supports on the final curved/spread skeleton.
    willow_anchor_distribution.install()

    foliage_assembly.install()
    foliage_assembly_lods.install()
    foliage_atlas_assembly.install()
    willow_foliage_fix.install()

    # The former radial strand-deletion pass is intentionally inactive.  Mature
    # Salix babylonica has a dense rounded crown; inner volume is created with
    # shorter curtains rather than deleting whole curtain groups.

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
    willow_foliage_fix.uninstall()
    foliage_atlas_assembly.uninstall()
    foliage_assembly_lods.uninstall()
    foliage_assembly.uninstall()
    willow_anchor_distribution.uninstall()
    willow_crown_spread.uninstall()
    willow_structure_motion.uninstall()
    willow_relay_architecture.uninstall()
    willow_architecture.uninstall()
    willow_relay_architecture.restore_preparation()
    branch_profiles.uninstall()
    advanced_growth.uninstall()
    appearance_state.uninstall()
    pbr_properties.unregister()
    foliage_sizing_properties.unregister()
    foliage_assembly_properties.unregister()
    branch_profile_properties.unregister()
    advanced_properties.unregister()
    properties.unregister()
