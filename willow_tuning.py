"""Target-driven structural and palette tuning for the weeping willow preset.

This module patches only WILLOW at registration so other species remain
untouched.  Values are tuned against a mature broad/rounded weeping-willow
reference rather than the generic umbrella profile.
"""

from . import pbr_profiles, presets, species_appearance


_INSTALLED = False
_OLD_PRESET = None
_OLD_PBR = None
_OLD_APPEARANCE = None


WILLOW_PRESET_TUNING = {
    # Broader-than-tall crown.  The ROUND profile gives long middle scaffold
    # branches over a wider height range; the weeping character is then created
    # by secondary/virtual branchlets instead of a narrow Gaussian umbrella.
    "height": 12.6,
    "base_radius": 0.68,
    # Structural motion works on the generated polyline.  Extra trunk samples
    # let the slow serpentine base/leader curvature remain visibly smooth.
    "trunk_segments": 28,
    "trunk_irregularity": 0.24,
    "trunk_taper": 1.16,
    "root_flare": 0.68,
    "crown_shape": "ROUND",
    "branch_distribution": "RANDOM",

    # A modest number of heavy scaffolds plus many finer descendants.  Stronger
    # trunk taper prevents the straight central leader from dominating the crown.
    "branch_levels": 4,
    "branch_start": 0.18,
    "primary_branches": 14,
    "secondary_per_branch": 4,
    "branch_angle": 1.28,
    "branch_length": 7.8,
    "branch_length_randomness": 0.30,
    "branch_bend": 0.38,
    "branch_droop": 0.27,
    "apical_dominance": 0.04,
    "phototropism": 0.10,
    "branch_collar": 0.40,
    "dead_branch_probability": 0.018,
    "prune_probability": 0.015,

    # Dense foliage over most of the outer half of the crown.  Smart willow
    # assembly keeps the lower central trunk open and creates the long fringe.
    "foliage_density": 1.80,
    "foliage_start": 0.24,
    "foliage_tip_bias": 0.48,
    "foliage_spread": 0.70,
    "leaf_up_bias": 0.20,

    # Smaller cards + more instances read as fine willow texture instead of
    # isolated ribbons.  Source cards remain single GN instances.
    "card_scale": 0.50,
    "card_aspect": 1.60,
    "card_style": "SINGLE",
}


WILLOW_PBR_TUNING = {
    # Dark saturated chlorophyll base with a controlled yellow-green highlight.
    # Dense overlap should create the target's deep green interior rather than
    # the pale lime appearance of the previous sparse crown.
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
