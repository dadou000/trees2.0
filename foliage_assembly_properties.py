import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty


class TREES2_PG_FoliageAssembly(bpy.types.PropertyGroup):
    enabled: BoolProperty(
        name="Smart Foliage Assembly",
        default=True,
        description=(
            "Use species-aware batched foliage assembly, branch-aligned card orientation, "
            "spacing control, and gravity-aware hanging foliage"
        ),
    )
    mode: EnumProperty(
        name="Assembly Mode",
        items=(
            ("AUTO", "Automatic by Species", "Choose an efficient assembly strategy from the species preset"),
            ("BROADLEAF", "Broadleaf Cluster", "Compact branch-aligned broadleaf clusters"),
            ("AIRY", "Airy Broadleaf", "Lower-density open clusters for birch/aspen/fine foliage"),
            ("WEEPING", "Weeping Curtains", "Gravity-driven hanging strands for willow-like foliage"),
            ("CONIFER", "Conifer Sprays", "Twig-aligned needle or scale sprays"),
            ("COLUMNAR", "Columnar Sprays", "Tight upward sprays for cypress-like forms"),
        ),
        default="AUTO",
    )
    density_budget: FloatProperty(
        name="Card Budget",
        default=1.0,
        min=0.25,
        max=2.0,
        description="Global multiplier for smart foliage card count",
    )
    spacing: FloatProperty(
        name="Minimum Spacing",
        default=1.0,
        min=0.25,
        max=2.5,
        description="Multiplier for spatial rejection distance between neighboring cluster anchors",
    )
    twig_alignment: FloatProperty(
        name="Twig Alignment",
        default=1.0,
        min=0.0,
        max=2.0,
        description="Multiplier for alignment of the card's long axis to the supporting twig",
    )
    outward_bias: FloatProperty(
        name="Outward Facing",
        default=1.0,
        min=0.0,
        max=2.0,
        description="Multiplier for canopy-outward card normals",
    )
    gravity_response: FloatProperty(
        name="Gravity Response",
        default=1.0,
        min=0.0,
        max=2.0,
        description="Multiplier for species-specific gravity/droop orientation",
    )
    angular_jitter: FloatProperty(
        name="Orientation Jitter",
        default=1.0,
        min=0.0,
        max=2.0,
        description="Multiplier for controlled local orientation variation",
    )
    force_single_sources: BoolProperty(
        name="Single-Card Sources",
        default=True,
        description=(
            "Use one plane per foliage instance. Smart assembly provides volume with multiple "
            "oriented instances instead of stacked cross/tri cards"
        ),
    )
    generated_atlas_aspect: BoolProperty(
        name="Auto Atlas Card Aspect",
        default=True,
        description="Use assembly-specific source-card aspect for Trees 2.0 generated atlases",
    )

    willow_length: FloatProperty(
        name="Willow Strand Length",
        default=1.0,
        min=0.35,
        max=1.8,
        description="Multiplier for hanging willow curtain length",
    )
    willow_ground_reach: FloatProperty(
        name="Ground Reach",
        default=0.92,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
        description="How strongly low outer willow strands are allowed to approach the ground",
    )
    willow_overlap: FloatProperty(
        name="Card Overlap",
        default=0.62,
        min=0.20,
        max=0.88,
        subtype="FACTOR",
        description=(
            "Target overlap between successive willow sprig cards. Higher values create "
            "denser, more continuous hanging curtains"
        ),
    )
    willow_spacing: FloatProperty(
        name="Coverage Spacing",
        default=1.0,
        min=0.55,
        max=1.75,
        description=(
            "Multiplier applied after overlap-derived willow card spacing. Values below 1 "
            "increase continuity and values above 1 reduce card count"
        ),
    )
    willow_flutter: FloatProperty(
        name="Strand Flutter",
        default=1.0,
        min=0.0,
        max=2.0,
        description="Multiplier for gentle lateral curvature of willow curtains",
    )
    willow_max_cards: IntProperty(
        name="Max Cards / Strand",
        default=18,
        min=3,
        max=32,
        description=(
            "Hard efficiency cap per hanging strand. Coverage-based spacing keeps the strand "
            "continuous even when the cap is reached"
        ),
    )
    write_debug_attributes: BoolProperty(
        name="Export Assembly Attributes",
        default=True,
        description="Write assembly role, source branch and strand progress attributes to foliage points",
    )


CLASSES = (TREES2_PG_FoliageAssembly,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.trees2_foliage_assembly = PointerProperty(type=TREES2_PG_FoliageAssembly)


def unregister():
    if hasattr(bpy.types.Scene, "trees2_foliage_assembly"):
        del bpy.types.Scene.trees2_foliage_assembly
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
