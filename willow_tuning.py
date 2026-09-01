"""Target-driven structural and palette tuning for the weeping willow preset.

This module patches only WILLOW at registration so other species remain
untouched.  The v0.8.7 values assume dedicated real topology, hierarchy-aware
structural motion, post-deformation radial anchor scoring and final strand-level
canopy shaping.
"""

from . import pbr_profiles, presets, species_appearance


_INSTALLED = False
_OLD_PRESET = None
_OLD_PBR = None
_OLD_APPEARANCE = None


WILLOW_PRESET_TUNING = {
    "height": 12.6,
    "base_radius": 0.72,
    "trunk_segments": 30,
    "trunk_irregularity": 0.30,
    "trunk_taper": 1.32,
    "root_flare": 0.82,
    "crown_shape": "ROUND",
    "branch_distribution": "RANDOM",

    # The 0.8.6 tree was still too fountain-like. Push the reduced set of real
    # generic primaries farther sideways; the co-dominant/fork layer supplies
    # the irregular hierarchy instead of adding more radial spokes.
    "branch_levels": 4,
    "branch_start": 0.23,
    "primary_branches": 9,
    "secondary_per_branch": 4,
    "branch_angle": 1.22,
    "branch_length": 7.5,
    "branch_length_randomness": 0.34,
    "branch_bend": 0.30,
    "branch_droop": 0.18,
    "apical_dominance": 0.03,
    "phototropism": 0.055,
    "branch_collar": 0.44,
    "dead_branch_probability": 0.015,
    "prune_probability": 0.012,

    # Slightly lower global density than 0.8.6 because the final radial pass now
    # deliberately moves the visual budget outward instead of filling the core.
    "foliage_density": 1.70,
    "foliage_start": 0.23,
    "foliage_tip_bias": 0.44,
    "foliage_spread": 0.76,
    "leaf_up_bias": 0.18,

    "card_scale": 0.50,
    "card_aspect": 1.60,
    "card_style": "SINGLE",
}


WILLOW_PBR_TUNING = {
    # The previous tree was still much brighter than the mature reference.
    # Keep chroma but lower luminance substantially; Respect Tree Colors derives
    # its default tint from this same palette, so atlas and shader stay coherent.
    "leaf_color": (0.030, 0.145, 0.012),
    "leaf_color_2": (0.145, 0.340, 0.040),
    "vein_color": (0.205, 0.430, 0.070),
    "leaf_roughness": 0.61,
    "leaf_normal_strength": 0.50,
    "twig_color": (0.18, 0.115, 0.042),
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
