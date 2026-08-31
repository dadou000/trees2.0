import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty


class TREES2_PG_FoliageSizing(bpy.types.PropertyGroup):
    enabled: BoolProperty(
        name="Position-Aware Size",
        default=True,
        description="Vary foliage-card size according to canopy exposure and position",
    )
    sizing_mode: EnumProperty(
        name="Sizing Profile",
        items=(
            ("AUTO", "Automatic by Species", "Choose a sun/shade sizing profile from the active species preset"),
            ("BROADLEAF", "Broadleaf", "Balanced broadleaf canopy sizing"),
            ("HEAVY", "Heavy / Oak", "Large interior masses with fine exposed silhouette foliage"),
            ("SLENDER", "Slender / Birch", "Moderate interior/edge size contrast"),
            ("WILLOW", "Flexible / Willow", "Fine exposed foliage for hanging crowns"),
            ("CONIFER", "Conifer", "More restrained card-size variation"),
            ("CUSTOM", "Custom", "Use the controls below directly"),
        ),
        default="AUTO",
    )

    strength: FloatProperty(
        name="Position Influence",
        default=1.0,
        min=0.0,
        max=1.5,
        description="Blend between uniform card size and the location-aware result",
    )
    interior_scale: FloatProperty(
        name="Interior / Shade Scale",
        default=1.18,
        min=0.25,
        max=3.0,
        description="Scale multiplier for sheltered foliage inside the crown",
    )
    silhouette_scale: FloatProperty(
        name="Silhouette / Sun Scale",
        default=0.70,
        min=0.20,
        max=2.0,
        description="Scale multiplier near the radial crown edge",
    )
    upper_crown_scale: FloatProperty(
        name="Upper Crown Scale",
        default=0.82,
        min=0.20,
        max=2.0,
        description="Additional size multiplier for exposed foliage near the top of the crown",
    )
    edge_start: FloatProperty(
        name="Edge Transition Start",
        default=0.58,
        min=0.10,
        max=1.10,
        description="Normalized crown radius where cards begin transitioning toward silhouette size",
    )
    top_start: FloatProperty(
        name="Upper Transition Start",
        default=0.72,
        min=0.10,
        max=0.98,
        description="Normalized crown height where the upper-canopy size reduction begins",
    )
    radial_influence: FloatProperty(
        name="Radial Influence",
        default=1.0,
        min=0.0,
        max=1.5,
        description="How strongly distance from the crown center affects card size",
    )
    vertical_influence: FloatProperty(
        name="Upper Exposure Influence",
        default=0.72,
        min=0.0,
        max=1.5,
        description="How strongly upper-canopy exposure affects card size",
    )
    crown_width_multiplier: FloatProperty(
        name="Crown Width Calibration",
        default=1.05,
        min=0.35,
        max=2.5,
        description="Calibration multiplier for the estimated local crown radius",
    )
    min_multiplier: FloatProperty(
        name="Minimum Multiplier",
        default=0.42,
        min=0.10,
        max=1.5,
        description="Lower safety clamp for position-based card scaling",
    )
    max_multiplier: FloatProperty(
        name="Maximum Multiplier",
        default=1.65,
        min=0.5,
        max=4.0,
        description="Upper safety clamp for position-based card scaling",
    )


CLASSES = (TREES2_PG_FoliageSizing,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.trees2_foliage_sizing = PointerProperty(type=TREES2_PG_FoliageSizing)


def unregister():
    if hasattr(bpy.types.Scene, "trees2_foliage_sizing"):
        del bpy.types.Scene.trees2_foliage_sizing
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
