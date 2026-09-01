bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 9, 2),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with research-based sympodial willow growth, outward-biased scaffold/foliage distribution, sinuous branches, direct PBR export, stable LODs, impostors, and GitHub updates",
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
    willow_outward_distribution,
    willow_relay_architecture,
    willow_sinuous_geometry,
    willow_structure_motion,
    willow_terminal_budget,
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

    # Research-based sympodial willow architecture: retain useful generic growth,
    # terminate the basal axis through relay growth, then clean the generic
    # recursive hierarchy so major structure occupies the outer crown instead of
    # accumulating as short spiderweb laterals near the central axes.
    willow_relay_architecture.prepare()
    willow_architecture.install()
    willow_relay_architecture.install()
    willow_outward_distribution.install()

    # Deform the retained hierarchy with correlated botanical motion, then give
    # visually important wood enough axial samples for genuinely sinuous curves.
    willow_structure_motion.install()
    willow_sinuous_geometry.install()

    # Broad-crown correction and final-skeleton virtual support scoring happen
    # after all structural deformation.  Real terminals classified as mid/inner
    # by the outward-distribution stage are then converted to reduced foliage
    # budgets, while outer terminals retain full curtain authority.
    willow_crown_spread.install()
    willow_anchor_distribution.install()
    willow_terminal_budget.install()

    foliage_assembly.install()
    foliage_assembly_lods.install()
    foliage_atlas_assembly.install()
    willow_foliage_fix.install()

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
    willow_terminal_budget.uninstall()
    willow_anchor_distribution.uninstall()
    willow_crown_spread.uninstall()
    willow_sinuous_geometry.uninstall()
    willow_structure_motion.uninstall()
    willow_outward_distribution.uninstall()
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
