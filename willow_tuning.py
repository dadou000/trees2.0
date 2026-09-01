"""Target-driven structural and palette tuning for the weeping willow preset.

This module deliberately patches only the WILLOW preset/profile at registration
so other species are unaffected.  It is installed after the general willow leaf
renderer, making these values the final defaults used when the user presses
Apply Species Preset or regenerates PBR textures.
"""

from . import pbr_profiles, presets, species_appearance


_INSTALLED = False
_OLD_PRESET = None
_OLD_PBR = None
_OLD_APPEARANCE = None


WILLOW_PRESET_TUNING = {
    # Keep a mature-but-not-gigantic tree, but make the crown substantially wider.
    "height": 13.5,
    "base_radius": 0.64,
    "trunk_irregularity": 0.24,
    "trunk_taper": 0.84,
    "root_flare": 0.50,
    "crown_shape": "UMBRELLA",
    "branch_distribution": "RANDOM",

    # Real weeping willows read as a handful of broad scaffold limbs carrying a
    # large number of finer branchlets, not dozens of equal radial spokes.
    "branch_levels": 4,
    "branch_start": 0.22,
    "primary_branches": 12,
    "secondary_per_branch": 4,
    "branch_angle": 1.30,
    "branch_length": 7.1,
    "branch_length_randomness": 0.34,
    "branch_bend": 0.33,

    # Heavy scaffold branches should arch/spread first.  Droop is progressively
    # multiplied by generation depth, so this lower base value makes the thin
    # third/fourth-order branchlets weep while keeping major limbs broad.
    "branch_droop": 0.34,
    "apical_dominance": 0.06,
    "phototropism": 0.10,
    "branch_collar": 0.38,
    "dead_branch_probability": 0.020,
    "prune_probability": 0.018,

    # More crown fill, less extreme tip-only population.  Smart willow assembly
    # then redistributes these terminals into short/mid curtain bundles.
    "foliage_density": 1.62,
    "foliage_start": 0.34,
    "foliage_tip_bias": 0.62,
    "foliage_spread": 0.62,
    "leaf_up_bias": 0.22,

    # Smaller, nearly uniform cards hide the card primitive and permit denser
    # volume for approximately the same silhouette cost.
    "card_scale": 0.56,
    "card_aspect": 1.65,
    "card_style": "SINGLE",
}


WILLOW_PBR_TUNING = {
    # Darker chlorophyll-rich base than the previous lime-biased default, with a
    # bright enough second color to retain local saturation and sunlit variation.
    "leaf_color": (0.075, 0.300, 0.030),
    "leaf_color_2": (0.285, 0.555, 0.085),
    "vein_color": (0.385, 0.625, 0.135),
    "leaf_roughness": 0.61,
    "leaf_normal_strength": 0.50,
    "twig_color": (0.18, 0.115, 0.045),
}


WILLOW_APPEARANCE_TUNING = {
    # A fuller sprig source card improves the dark overlapping mass of a willow
    # curtain without changing individual blade scale.
    "leaf_count": 10,
    "leaf_aspect": 4.35,
    "serration": 0.035,
    "tip_sharpness": 0.95,
    "morphology_label": "Willow alternate lanceolate leaves on a pendulous sprig",
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
