"""Species appearance rules shared by presets, PBR synthesis and materials.

The structural tree preset controls crown/branch architecture.  This module
controls the visual identity of the foliage: blade silhouette, compound-leaf
arrangement, conifer spray style and the default bark/foliage colors.
"""


def _merge(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


DEFAULT = {
    "leaf_shape": "OVAL",
    "arrangement": "CLUSTER",
    "leaf_aspect": 1.35,
    "leaf_count": 5,
    "serration": 0.10,
    "lobes": 0,
    "lobe_depth": 0.0,
    "tip_sharpness": 0.45,
    "base_notch": 0.0,
    "asymmetry": 0.03,
    "leaflet_scale": 1.0,
    "fascicle_size": 2,
    "morphology_label": "Oval broadleaf",
}


# Every PRESET_ITEMS id is represented explicitly.  The blade shape describes
# an individual leaf/leaflet while arrangement describes how those blades are
# assembled into the foliage-card atlas.
SPECIES_APPEARANCE = {
    "GENERIC": DEFAULT,
    "OAK": _merge(DEFAULT, leaf_shape="OAK_LOBED", leaf_aspect=1.15, leaf_count=5,
                  lobes=5, lobe_depth=0.48, serration=0.035, tip_sharpness=0.38,
                  morphology_label="English oak lobed leaf"),
    "HOLM_OAK": _merge(DEFAULT, leaf_shape="ELLIPTIC_POINTED", leaf_aspect=1.80,
                       leaf_count=6, serration=0.22, tip_sharpness=0.72,
                       morphology_label="Holm oak leathery elliptic leaf"),
    "CORK_OAK": _merge(DEFAULT, leaf_shape="ELLIPTIC_POINTED", leaf_aspect=1.52,
                       leaf_count=6, serration=0.16, tip_sharpness=0.58,
                       morphology_label="Cork oak ovate leaf"),
    "BIRCH": _merge(DEFAULT, leaf_shape="DELTOID", leaf_aspect=1.10, leaf_count=6,
                    serration=0.31, tip_sharpness=0.82,
                    morphology_label="Birch triangular serrated leaf"),
    "BEECH": _merge(DEFAULT, leaf_shape="ELLIPTIC_POINTED", leaf_aspect=1.43,
                    leaf_count=5, serration=0.055, tip_sharpness=0.56,
                    morphology_label="Beech elliptic leaf"),
    "MAPLE": _merge(DEFAULT, leaf_shape="PALMATE", leaf_aspect=1.0, leaf_count=4,
                    lobes=5, lobe_depth=0.58, serration=0.07, tip_sharpness=0.90,
                    morphology_label="Five-lobed maple leaf"),
    "ASH": _merge(DEFAULT, leaf_shape="ELLIPTIC_POINTED", arrangement="PINNATE",
                  leaf_aspect=1.85, leaf_count=9, serration=0.10, leaflet_scale=0.82,
                  tip_sharpness=0.72, morphology_label="Ash pinnate compound leaf"),
    "ELM": _merge(DEFAULT, leaf_shape="ELLIPTIC_POINTED", leaf_aspect=1.62,
                  leaf_count=5, serration=0.34, asymmetry=0.10, tip_sharpness=0.74,
                  morphology_label="Elm asymmetric serrated leaf"),
    "LINDEN": _merge(DEFAULT, leaf_shape="HEART", leaf_aspect=1.06, leaf_count=5,
                     serration=0.12, base_notch=0.72, tip_sharpness=0.74,
                     morphology_label="Linden heart-shaped leaf"),
    "CHESTNUT": _merge(DEFAULT, leaf_shape="LANCE", leaf_aspect=2.45, leaf_count=5,
                       serration=0.43, tip_sharpness=0.88,
                       morphology_label="Sweet chestnut long serrated leaf"),
    "WALNUT": _merge(DEFAULT, leaf_shape="ELLIPTIC_POINTED", arrangement="PINNATE",
                     leaf_aspect=1.75, leaf_count=7, serration=0.02, leaflet_scale=0.92,
                     tip_sharpness=0.62, morphology_label="Walnut pinnate compound leaf"),
    "PLANE": _merge(DEFAULT, leaf_shape="PALMATE", leaf_aspect=1.0, leaf_count=4,
                    lobes=5, lobe_depth=0.52, serration=0.08, tip_sharpness=0.82,
                    morphology_label="Plane palmate five-lobed leaf"),
    "ALDER": _merge(DEFAULT, leaf_shape="ROUND", leaf_aspect=1.02, leaf_count=6,
                    serration=0.23, tip_sharpness=0.18,
                    morphology_label="Alder rounded serrated leaf"),
    "ASPEN": _merge(DEFAULT, leaf_shape="ROUND", leaf_aspect=1.0, leaf_count=6,
                    serration=0.16, tip_sharpness=0.35,
                    morphology_label="Aspen rounded leaf"),
    "POPLAR": _merge(DEFAULT, leaf_shape="DELTOID", leaf_aspect=1.18, leaf_count=6,
                     serration=0.15, tip_sharpness=0.76,
                     morphology_label="Poplar deltoid leaf"),
    "WILLOW": _merge(DEFAULT, leaf_shape="LANCE", arrangement="WEEPING_SPRIG",
                     leaf_aspect=4.45, leaf_count=8, serration=0.035,
                     tip_sharpness=0.94,
                     morphology_label="Willow alternate lanceolate leaves on a pendulous sprig"),
    "CHERRY": _merge(DEFAULT, leaf_shape="ELLIPTIC_POINTED", leaf_aspect=1.58,
                     leaf_count=5, serration=0.22, tip_sharpness=0.70,
                     morphology_label="Cherry elliptic serrated leaf"),
    "APPLE": _merge(DEFAULT, leaf_shape="OVAL", leaf_aspect=1.50, leaf_count=5,
                    serration=0.14, tip_sharpness=0.48,
                    morphology_label="Apple ovate leaf"),
    "MAGNOLIA": _merge(DEFAULT, leaf_shape="ELLIPTIC_POINTED", leaf_aspect=1.92,
                       leaf_count=4, serration=0.0, tip_sharpness=0.42,
                       morphology_label="Magnolia large entire leaf"),
    "JACARANDA": _merge(DEFAULT, leaf_shape="OVAL", arrangement="BIPINNATE",
                        leaf_aspect=1.75, leaf_count=18, serration=0.0,
                        leaflet_scale=0.42, tip_sharpness=0.40,
                        morphology_label="Jacaranda bipinnate fine leaflets"),
    "EUCALYPTUS": _merge(DEFAULT, leaf_shape="LANCE", leaf_aspect=3.15, leaf_count=6,
                         serration=0.0, asymmetry=0.12, tip_sharpness=0.88,
                         morphology_label="Eucalyptus curved lanceolate leaf"),
    "OLIVE": _merge(DEFAULT, leaf_shape="LANCE", leaf_aspect=3.60, leaf_count=7,
                    serration=0.0, tip_sharpness=0.82,
                    morphology_label="Olive narrow leathery leaf"),
    "ACACIA": _merge(DEFAULT, leaf_shape="OVAL", arrangement="BIPINNATE",
                     leaf_aspect=1.70, leaf_count=20, serration=0.0,
                     leaflet_scale=0.38, tip_sharpness=0.34,
                     morphology_label="Acacia bipinnate tiny leaflets"),
    "BAOBAB": _merge(DEFAULT, leaf_shape="ELLIPTIC_POINTED", arrangement="PALMATE_COMPOUND",
                     leaf_aspect=1.55, leaf_count=7, serration=0.0,
                     leaflet_scale=0.88, tip_sharpness=0.64,
                     morphology_label="Baobab palmate compound leaf"),
    "PINE": _merge(DEFAULT, leaf_shape="NEEDLE", arrangement="NEEDLE_FASCICLE",
                   leaf_aspect=5.0, leaf_count=14, serration=0.0, fascicle_size=2,
                   morphology_label="Scots pine paired needle fascicles"),
    "STONE_PINE": _merge(DEFAULT, leaf_shape="NEEDLE", arrangement="NEEDLE_FASCICLE",
                         leaf_aspect=5.8, leaf_count=16, serration=0.0, fascicle_size=2,
                         morphology_label="Stone pine paired long needles"),
    "SPRUCE": _merge(DEFAULT, leaf_shape="NEEDLE", arrangement="NEEDLE_RADIAL",
                     leaf_aspect=3.4, leaf_count=18, serration=0.0,
                     morphology_label="Spruce radial single needles"),
    "FIR": _merge(DEFAULT, leaf_shape="NEEDLE", arrangement="NEEDLE_FLAT",
                  leaf_aspect=3.0, leaf_count=17, serration=0.0,
                  morphology_label="Fir flat two-ranked needles"),
    "CEDAR": _merge(DEFAULT, leaf_shape="NEEDLE", arrangement="NEEDLE_ROSETTE",
                    leaf_aspect=3.1, leaf_count=18, serration=0.0,
                    morphology_label="Cedar needle rosettes"),
    "CYPRESS": _merge(DEFAULT, leaf_shape="SCALE", arrangement="SCALE_SPRAY",
                      leaf_aspect=2.4, leaf_count=22, serration=0.0,
                      morphology_label="Cypress scale-leaf sprays"),
    "REDWOOD": _merge(DEFAULT, leaf_shape="NEEDLE", arrangement="NEEDLE_FLAT",
                      leaf_aspect=3.6, leaf_count=19, serration=0.0,
                      morphology_label="Coast redwood flat linear needles"),
    "DEAD_TREE": _merge(DEFAULT, leaf_shape="NONE", arrangement="NONE", leaf_count=0,
                        morphology_label="No foliage"),
    "WINDSWEPT": _merge(DEFAULT, leaf_shape="OVAL", leaf_aspect=1.55, leaf_count=4,
                        serration=0.10, morphology_label="Weathered broadleaf"),
    "SAPLING": _merge(DEFAULT, leaf_shape="OVAL", leaf_aspect=1.45, leaf_count=5,
                      serration=0.08, morphology_label="Young broadleaf"),
}


def _mix3(a, b, t):
    return tuple(float(a[i]) * (1.0 - t) + float(b[i]) * t for i in range(3))


def appearance_profile(species, pbr_profile=None):
    """Return morphology plus default colors for a species.

    Colors are derived from the existing PBR profile so the texture generator,
    species preset and final shader all start from the same palette.
    """
    species = str(species)
    result = dict(SPECIES_APPEARANCE.get(species, DEFAULT))
    if pbr_profile:
        # Existing PBR profiles still own bark physics and detailed palette.
        for key, value in pbr_profile.items():
            if key not in {
                "leaf_shape", "leaf_aspect", "leaf_count", "serration", "lobes"
            }:
                result.setdefault(key, value)
        c1 = pbr_profile.get("leaf_color")
        c2 = pbr_profile.get("leaf_color_2")
        if c1 and c2:
            result["default_leaf_tint"] = _mix3(c1, c2, 0.42)
        elif c1:
            result["default_leaf_tint"] = tuple(c1)
        bark = pbr_profile.get("bark_base")
        if bark:
            result["default_bark_tint"] = tuple(bark)
        # Preserve all physics/detail fields while forcing morphology fields
        # to the explicit species appearance above.
        merged = dict(pbr_profile)
        merged.update(result)
        result = merged
    return result
