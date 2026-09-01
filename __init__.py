bl_info = {
    "name": "Trees 2.0",
    "author": "dadou000",
    "version": (0, 8, 5),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Trees 2.0",
    "description": "Procedural game-ready trees with hierarchy-aware chaotic willow structure, broad rounded canopies, virtual drooping branchlets, volumetric curtain bundles, direct 16-bit PBR export, stable LODs, impostors, and GitHub updates",
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
    willow_architecture,
    willow_bark_synthesis,
    willow_foliage_fix,
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

    # Deform the final botanical skeleton first.  The wrapper is hierarchy-aware:
    # child attachments are remapped onto already-curved parents before their
    # own level-dependent wander and distal droop are integrated.
    willow_structure_motion.install()

    # Virtual willow foliage supports are selected after structural deformation,
    # so their height/exposure scoring reflects the actual curved scaffold.
    willow_architecture.install()

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

    # Final willow defaults are target-driven. Install after the general leaf
    # renderer so the structural and palette tuning is the final species state.
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
    willow_architecture.uninstall()
    willow_structure_motion.uninstall()
    branch_profiles.uninstall()
    advanced_growth.uninstall()
    appearance_state.uninstall()
    pbr_properties.unregister()
    foliage_sizing_properties.unregister()
    foliage_assembly_properties.unregister()
    branch_profile_properties.unregister()
    advanced_properties.unregister()
    properties.unregister()
