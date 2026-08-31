import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty


class TREES2_PG_AdvancedSettings(bpy.types.PropertyGroup):
    use_space_colonization: BoolProperty(
        name="Space Competition",
        default=True,
        description="Steer branch growth toward unoccupied crown space and away from existing branches",
    )
    attraction_points: IntProperty(
        name="Attraction Points", default=700, min=64, max=8000,
        description="Number of virtual canopy targets used by competition growth",
    )
    attraction_influence: FloatProperty(
        name="Influence Radius", default=2.8, min=0.1, max=20.0, unit="LENGTH",
        description="Distance within which canopy targets attract branch growth",
    )
    attraction_kill_distance: FloatProperty(
        name="Claim Radius", default=0.65, min=0.03, max=8.0, unit="LENGTH",
        description="Targets closer than this are consumed after a branch occupies that space",
    )
    competition_clearance: FloatProperty(
        name="Branch Clearance", default=0.32, min=0.02, max=5.0, unit="LENGTH",
        description="Minimum preferred separation from already occupied branch space",
    )
    attraction_strength: FloatProperty(name="Attraction Strength", default=0.62, min=0.0, max=2.0)
    avoidance_strength: FloatProperty(name="Avoidance Strength", default=1.05, min=0.0, max=3.0)
    competition_lod_max: IntProperty(
        name="Competition Through LOD", default=2, min=0, max=4,
        description="Highest numeric LOD that uses competition growth",
    )

    junction_mode: EnumProperty(
        name="Junction Geometry",
        items=(
            ("COLLAR", "Fast Collars", "Keep intersecting branch tubes with enlarged collars"),
            (
                "EXACT_BOOLEAN",
                "Exact Boolean Junctions",
                "Union trunk and major branches with Blender's Exact Boolean solver without remeshing the whole tree",
            ),
        ),
        default="EXACT_BOOLEAN",
    )
    junction_boolean_level_max: IntProperty(
        name="Exact Through Branch Level",
        default=2,
        min=1,
        max=4,
        description="Highest branch hierarchy level fused with Exact Boolean; thinner branches remain cheap collar geometry",
    )
    junction_boolean_lod_max: IntProperty(
        name="Exact Through LOD",
        default=1,
        min=0,
        max=4,
        description="Highest numeric LOD that receives Exact Boolean junctions",
    )
    reproject_branch_attributes: BoolProperty(
        name="Reproject Attributes", default=True,
        description="Reproject branch hierarchy and wind attributes after topology-changing Boolean unions",
    )

    impostor_views: IntProperty(
        name="Views", default=8, min=4, max=32,
        description="Number of azimuth directions rendered into the impostor atlas",
    )
    impostor_resolution: IntProperty(
        name="Tile Resolution", default=256, min=64, max=2048,
        description="Resolution of each square impostor view",
    )
    impostor_elevation: FloatProperty(
        name="Camera Elevation", default=math.radians(7.0), min=math.radians(-30.0), max=math.radians(45.0), subtype="ANGLE",
    )
    impostor_padding: FloatProperty(name="Frame Padding", default=0.08, min=0.0, max=0.5, subtype="FACTOR")
    impostor_output_dir: StringProperty(
        name="Output Folder", subtype="DIR_PATH", default="",
        description="Blank uses the .blend directory, or the system temporary directory for an unsaved file",
    )
    create_impostor_mesh: BoolProperty(
        name="Create Billboard Mesh", default=True,
        description="Create a tiny multi-plane view-selecting billboard mesh using the baked atlas",
    )
    replace_lod4_with_impostor: BoolProperty(
        name="Impostor as LOD4", default=True,
        description="Generate LOD0-LOD3 plus a baked multi-view impostor when using Generate LOD Set",
    )


CLASSES = (TREES2_PG_AdvancedSettings,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.trees2_advanced_settings = PointerProperty(type=TREES2_PG_AdvancedSettings)


def unregister():
    if hasattr(bpy.types.Scene, "trees2_advanced_settings"):
        del bpy.types.Scene.trees2_advanced_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
