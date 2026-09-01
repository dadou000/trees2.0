"""Research-driven structural and palette tuning for the weeping willow preset.

0.9.0 assumes sympodial relay axes: the basal trunk terminates, vigorous distal
shoots continue height, and obliquely upright lateral scaffolds support the
strongly pendulous fine crown.  Other species remain untouched.
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
    "trunk_taper": 1.28,
    "root_flare": 0.82,
    "crown_shape": "ROUND",
    "branch_distribution": "RANDOM",

    # Heavy willow scaffolds are obliquely upright at origin.  The hierarchy-
    # aware motion layer supplies progressively stronger distal gravity to fine
    # branches, rather than making the major limbs horizontal at birth.
    "branch_levels": 4,
    "branch_start": 0.18,
    "primary_branches": 10,
    "secondary_per_branch": 4,
    "branch_angle": 0.96,
    "branch_length": 6.8,
    "branch_length_randomness": 0.34,
    "branch_bend": 0.29,
    "branch_droop": 0.11,
    "apical_dominance": 0.16,
    "phototropism": 0.14,
    "branch_collar": 0.44,
    "dead_branch_probability": 0.015,
    "prune_probability": 0.012,

    # Salix babylonica forms a dense broad crown.  Keep abundant real terminal
    # growth and bias the longest curtains distally instead of hollowing the core.
    "foliage_density": 1.86,
    "foliage_start": 0.25,
    "foliage_tip_bias": 0.56,
    "foliage_spread": 0.74,
    "leaf_up_bias": 0.16,

    "card_scale": 0.50,
    "card_aspect": 1.60,
    "card_style": "SINGLE",
}


WILLOW_PBR_TUNING = {
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
