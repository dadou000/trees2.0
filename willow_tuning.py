"""Target-driven structural and palette tuning for the weeping willow preset.

This module patches only WILLOW at registration so other species remain
untouched.  The v0.8.6 values assume the dedicated architecture layer supplies
low co-dominant leaders, real intermediate forks and buttress roots.  Therefore
the generic radial skeleton can be simpler and less spoke-like.
"""

from . import pbr_profiles, presets, species_appearance


_INSTALLED = False
_OLD_PRESET = None
_OLD_PBR = None
_OLD_APPEARANCE = None


WILLOW_PRESET_TUNING = {
    "height": 12.6,
    "base_radius": 0.72,
    # High sampling is useful because structural motion bends the trunk after
    # botanical growth.  Faster taper lets low co-dominant limbs take over the
    # crown instead of leaving one thick pole visible to the apex.
    "trunk_segments": 30,
    "trunk_irregularity": 0.30,
    "trunk_taper": 1.32,
    "root_flare": 0.82,
    "crown_shape": "ROUND",
    "branch_distribution": "RANDOM",

    # Fewer generic primaries.  The architecture layer adds a small number of
    # deliberately placed leaders and intermediate forks, producing clustered
    # asymmetry rather than an evenly populated radial star.
    "branch_levels": 4,
    "branch_start": 0.23,
    "primary_branches": 9,
    "secondary_per_branch": 4,
    "branch_angle": 1.10,
    "branch_length": 7.0,
    "branch_length_randomness": 0.34,
    # Base growth stays comparatively calm; hierarchy-aware motion supplies the
    # large sweep, direction changes and fine-branch chaos afterwards.
    "branch_bend": 0.30,
    "branch_droop": 0.20,
    "apical_dominance": 0.03,
    "phototropism": 0.07,
    "branch_collar": 0.44,
    "dead_branch_probability": 0.015,
    "prune_probability": 0.012,

    # Keep the successful v0.8.x curtain density, but distribute it over the new
    # real woody forks and virtual supports rather than compensating with larger
    # cards.
    "foliage_density": 1.78,
    "foliage_start": 0.23,
    "foliage_tip_bias": 0.46,
    "foliage_spread": 0.72,
    "leaf_up_bias": 0.20,

    "card_scale": 0.50,
    "card_aspect": 1.60,
    "card_style": "SINGLE",
}


WILLOW_PBR_TUNING = {
    "leaf_color": (0.050, 0.220, 0.022),
    "leaf_color_2": (0.205, 0.455, 0.065),
    "vein_color": (0.300, 0.535, 0.095),
    "leaf_roughness": 0.59,
    "leaf_normal_strength": 0.50,
    "twig_color": (0.20, 0.13, 0.050),
}


WILLOW_APPEARANCE_TUNING = {
    "leaf_count": 11,
    "leaf_aspect": 4.35,
    "serration": 0.035,
    "tip_sharpness": 0.95,
    "morphology_label": "Willow alternate linear-lanceolate leaves on a pendulous sprig",
}


def install():
    global _INSTALLED, _OLD_PRESET, _OLD_PBR, _OLD_APPEARANCE
    if _INSTALLED:
        return

    preset = presets.PRESETS.get("WILLOW")
    profile = pbr_profiles.SPECIES_PBR.get("WILLOW")
    appearance = species_appearance.SPECIES_APPEARANCE.get("WILLOW")
    if preset is None or profile is None or appearance is None:
        return

    _OLD_PRESET = dict(preset)
    _OLD_PBR = dict(profile)
    _OLD_APPEARANCE = dict(appearance)

    preset.update(WILLOW_PRESET_TUNING)
    profile.update(WILLOW_PBR_TUNING)
    appearance.update(WILLOW_APPEARANCE_TUNING)
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return

    if _OLD_PRESET is not None:
        presets.PRESETS["WILLOW"].clear()
        presets.PRESETS["WILLOW"].update(_OLD_PRESET)
    if _OLD_PBR is not None:
        pbr_profiles.SPECIES_PBR["WILLOW"].clear()
        pbr_profiles.SPECIES_PBR["WILLOW"].update(_OLD_PBR)
    if _OLD_APPEARANCE is not None:
        species_appearance.SPECIES_APPEARANCE["WILLOW"].clear()
        species_appearance.SPECIES_APPEARANCE["WILLOW"].update(_OLD_APPEARANCE)
    _INSTALLED = False
