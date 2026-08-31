PRESETS = {
    "GENERIC": {
        "height": 12.0, "base_radius": 0.45, "trunk_irregularity": 0.12, "trunk_taper": 0.92,
        "root_flare": 0.35, "crown_shape": "ROUND", "branch_start": 0.24, "primary_branches": 20,
        "secondary_per_branch": 3, "branch_angle": 1.02, "branch_length": 4.4, "branch_bend": 0.16,
        "branch_droop": 0.16, "apical_dominance": 0.42, "phototropism": 0.18,
        "foliage_density": 1.0, "foliage_tip_bias": 0.65, "foliage_spread": 0.55,
        "card_scale": 0.72, "card_aspect": 1.25, "card_style": "CROSS",
    },
    "OAK": {
        "height": 15.0, "base_radius": 0.72, "trunk_irregularity": 0.22, "trunk_taper": 0.82,
        "root_flare": 0.65, "crown_shape": "ROUND", "branch_start": 0.28, "primary_branches": 18,
        "secondary_per_branch": 4, "branch_angle": 1.12, "branch_length": 6.5, "branch_bend": 0.28,
        "branch_droop": 0.12, "apical_dominance": 0.18, "phototropism": 0.12,
        "branch_collar": 0.55, "foliage_density": 1.15, "foliage_tip_bias": 0.58,
        "foliage_spread": 0.75, "card_scale": 0.82, "card_aspect": 1.15, "card_style": "TRI",
    },
    "BIRCH": {
        "height": 16.0, "base_radius": 0.34, "trunk_irregularity": 0.10, "trunk_taper": 1.05,
        "root_flare": 0.22, "crown_shape": "OVAL", "branch_start": 0.34, "primary_branches": 24,
        "secondary_per_branch": 3, "branch_angle": 0.86, "branch_length": 3.5, "branch_bend": 0.14,
        "branch_droop": 0.28, "apical_dominance": 0.62, "phototropism": 0.28,
        "foliage_density": 0.88, "foliage_tip_bias": 0.72, "foliage_spread": 0.48,
        "card_scale": 0.55, "card_aspect": 1.45, "card_style": "CROSS",
    },
    "POPLAR": {
        "height": 22.0, "base_radius": 0.48, "trunk_irregularity": 0.055, "trunk_taper": 1.12,
        "root_flare": 0.25, "crown_shape": "COLUMNAR", "branch_start": 0.18, "primary_branches": 34,
        "secondary_per_branch": 2, "branch_angle": 0.56, "branch_length": 2.8, "branch_bend": 0.08,
        "branch_droop": 0.02, "apical_dominance": 0.86, "phototropism": 0.52,
        "foliage_density": 1.05, "foliage_tip_bias": 0.70, "foliage_spread": 0.38,
        "card_scale": 0.58, "card_aspect": 1.35, "card_style": "CROSS",
    },
    "WILLOW": {
        "height": 13.0, "base_radius": 0.58, "trunk_irregularity": 0.20, "trunk_taper": 0.88,
        "root_flare": 0.42, "crown_shape": "UMBRELLA", "branch_start": 0.30, "primary_branches": 22,
        "secondary_per_branch": 4, "branch_angle": 1.20, "branch_length": 6.0, "branch_bend": 0.24,
        "branch_droop": 0.95, "apical_dominance": 0.14, "phototropism": -0.04,
        "foliage_density": 1.35, "foliage_tip_bias": 0.80, "foliage_spread": 0.45,
        "card_scale": 0.68, "card_aspect": 1.75, "card_style": "CROSS",
    },
    "PINE": {
        "height": 20.0, "base_radius": 0.52, "trunk_irregularity": 0.055, "trunk_taper": 1.18,
        "root_flare": 0.30, "crown_shape": "CONICAL", "branch_start": 0.18, "primary_branches": 36,
        "secondary_per_branch": 3, "branch_angle": 1.28, "branch_length": 5.5, "branch_bend": 0.08,
        "branch_droop": 0.22, "apical_dominance": 0.88, "phototropism": 0.12,
        "foliage_density": 1.45, "foliage_tip_bias": 0.70, "foliage_spread": 0.30,
        "card_scale": 0.62, "card_aspect": 1.70, "card_style": "TRI",
    },
}


def apply_preset(settings, name):
    preset = PRESETS.get(name)
    if not preset:
        return False
    for key, value in preset.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    return True
