bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 9, 7),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with continuous willow relay handoffs, viable structural limbs, hierarchy-balanced branches, corrected foliage cards, organic junctions, two-mesh runtime export, and GPU mappings",
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
    game_asset_export,
    game_asset_properties,
    game_asset_runtime,
    game_asset_ui,
    junction_surface_fairing,
    leaf_synthesis,
    leaf_synthesis_runtime,
    operators,
    organic_junctions,
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
    willow_branch_viability,
    willow_card_orientation,
    willow_crown_envelope,
    willow_crown_spread,
    willow_foliage_fix,
    willow_hierarchy_balance,
    willow_leaf_synthesis,
    willow_outward_distribution,
    willow_relay_architecture,
    willow_relay_handoff,
    willow_sinuous_geometry,
    willow_structure_motion,
    willow_terminal_budget,
    willow_tuning,
)


def register():
    properties.register()
    game_asset_properties.register()
    advanced_properties.register()
    branch_profile_properties.register()
    foliage_assembly_properties.register()
    foliage_sizing_properties.register()
    pbr_properties.register()
    appearance_state.install()
    advanced_growth.install()
    branch_profiles.install()

    # Build the sympodial relay topology, then immediately convert the first
    # takeover into a true trunk continuation: the obsolete parent axis becomes
    # only a short tapered nub and the relay inherits parent tangent/diameter.
    willow_relay_architecture.prepare()
    willow_architecture.install()
    willow_relay_architecture.install()
    willow_relay_handoff.install()
    willow_outward_distribution.install()

    # Deform the retained hierarchy with correlated botanical motion, then give
    # visually important wood enough axial samples for genuinely sinuous curves.
    willow_structure_motion.install()
    willow_sinuous_geometry.install()

    # Broad-crown shaping runs on the final curved wood. Then enforce parent /
    # child dimensional hierarchy and finally reject the remaining pathological
    # thick-short-bare terminal limb cases before foliage-support scoring.
    willow_crown_spread.install()
    willow_hierarchy_balance.install()
    willow_branch_viability.install()

    # Final-skeleton virtual support scoring and crown envelope use the corrected
    # hierarchy, so foliage density cannot hide or amplify an impossible branch
    # relationship.
    willow_anchor_distribution.install()
    willow_crown_envelope.install()
    willow_terminal_budget.install()

    # Shape parent/child roots in the branch graph itself before foliage points or
    # game-runtime metadata are derived from it. This removes abrupt first-ring
    # collar cliffs and adds bounded parent flare around substantial inserts.
    organic_junctions.install()

    foliage_assembly.install()
    foliage_assembly_lods.install()
    foliage_atlas_assembly.install()
    willow_foliage_fix.install()

    # The willow atlas root lives at card +Z/high V while the physical hanging
    # direction is root->tip. Flip the card-local Y/Z convention once, after all
    # foliage generators, so leaf tips remain gravity-facing at every LOD.
    willow_card_orientation.install()

    foliage_sizing.install()
    exact_junctions.install()

    # Exact Boolean removes interior overlap; this final local relaxation removes
    # the remaining polygonal saddle/ridge only around major fused junctions.
    junction_surface_fairing.install()

    # Runtime mapping is deliberately installed after every geometry/foliage
    # wrapper. It records the final branch graph, longitudinal wood coordinates
    # and foliage support bindings without changing the visible authoring tree.
    game_asset_runtime.install()

    advanced_operators.register()
    operators.register()
    game_asset_export.GENERATOR_VERSION = "0.9.7"
    game_asset_export.register()
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
    game_asset_ui.register()
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
    game_asset_ui.unregister()
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
    game_asset_export.unregister()
    operators.unregister()
    advanced_operators.unregister()
    game_asset_runtime.uninstall()
    junction_surface_fairing.uninstall()
    exact_junctions.uninstall()
    foliage_sizing.uninstall()
    willow_card_orientation.uninstall()
    willow_foliage_fix.uninstall()
    foliage_atlas_assembly.uninstall()
    foliage_assembly_lods.uninstall()
    foliage_assembly.uninstall()
    organic_junctions.uninstall()
    willow_terminal_budget.uninstall()
    willow_crown_envelope.uninstall()
    willow_anchor_distribution.uninstall()
    willow_branch_viability.uninstall()
    willow_hierarchy_balance.uninstall()
    willow_crown_spread.uninstall()
    willow_sinuous_geometry.uninstall()
    willow_structure_motion.uninstall()
    willow_outward_distribution.uninstall()
    willow_relay_handoff.uninstall()
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
    game_asset_properties.unregister()
    properties.unregister()
