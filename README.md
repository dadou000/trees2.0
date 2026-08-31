# Trees 2.0

A Blender **5.2 LTS** extension for generating game-ready procedural trees without millions of individually modeled leaves.

Trees 2.0 combines low-sided woody geometry, instanced 2D foliage cards, competition-guided crown growth, manifold branch fusion, generated LODs, wind metadata, and automatic multi-view impostors.

## Status

`0.3.0` is the current development version. Python syntax is checked in CI. Blender-runtime behavior should still be treated as beta until the new voxel-fusion and render-baking paths have been exercised on several Blender 5.2 scenes and hardware configurations.

## Installation

1. Download or clone the repository.
2. Package the extension so `blender_manifest.toml` and `__init__.py` are at the ZIP root.
3. In Blender 5.2 open **Edit > Preferences > Get Extensions > Install from Disk**.
4. Enable **Trees 2.0** if needed.
5. Open the 3D View sidebar (`N`) and choose **Trees 2.0**.

The extension requests Blender's **files** permission because the impostor baker writes PNG atlases to disk.

## Main systems

### Procedural structure

The deterministic tree skeleton supports:

- root flare,
- trunk taper and irregularity,
- 1–4 branch levels,
- phyllotaxis, random, and whorled branch distribution,
- round, oval, columnar, conical, vase, and umbrella crowns,
- branch bend and droop,
- phototropism/upward growth,
- apical dominance,
- natural pruning,
- dead branches,
- branch collars.

### Competition / space-colonization growth

When **Space Competition** is enabled, Trees 2.0 samples virtual attraction points throughout the crown volume. Growing branches are pulled toward nearby unclaimed targets while an occupied-space field repels them from existing woody segments.

New growth consumes nearby attraction points, so later branches preferentially fill empty canopy volume instead of repeatedly crossing existing limbs.

Controls include attraction-point count, influence radius, claim radius, branch clearance, attraction strength, avoidance strength, and the highest LOD that should run the competition pass.

### Real parent/child junctions

**Fused Manifold** mode runs Blender's voxel remesher on the generated woody shells. Overlapping parent/child tubes become one continuous manifold volume instead of remaining separate intersecting shells.

After fusion Trees 2.0 reprojects the original branch hierarchy and wind attributes using nearest-point lookup. Bark images use box projection in fused mode because remeshing necessarily rebuilds topology.

For distant LODs you can keep the cheaper collar/intersection method.

### 2D foliage cards

Leaves are not modeled individually. Terminal living branches instance shared foliage cards through Geometry Nodes.

Card modes:

- **Single** — one bent card,
- **Crossed** — two crossed cards,
- **Tri-Cross** — three crossed cards.

A foliage card should normally represent several leaves and small twigs.

### Texture-atlas variation

Configure Atlas Columns, Atlas Rows and Used Cells. Trees 2.0 builds one shared source card per used atlas cell and assigns every foliage point a `trees2_atlas_index` attribute. Geometry Nodes uses **Pick Instance** to choose the corresponding UV-mapped source.

Supported maps:

- leaf color + alpha,
- leaf normal,
- leaf roughness,
- bark color,
- bark normal.

### Species and form presets

The preset library includes more than thirty starting forms, including:

- English, holm and cork oak,
- birch, beech, maple, ash, elm, linden, chestnut and walnut,
- poplar, willow, cherry, apple and magnolia,
- eucalyptus, olive, acacia and baobab,
- Scots pine, stone pine, spruce, fir, cedar, Italian cypress and coast redwood,
- dead tree, windswept and sapling forms.

These are parameterized shape presets, not scanned species assets.

## LOD pipeline

| LOD | Purpose | Default behavior |
| --- | --- | --- |
| LOD0 | Hero | Full branch depth, competition growth, close foliage |
| LOD1 | Near | Reduced radial/detail density, optional fused junctions |
| LOD2 | Mid | Reduced branch depth and foliage |
| LOD3 | Far | Minimal geometric tree |
| LOD4 | Impostor | Multi-view baked atlas + very-low-cost billboard mesh |

With **Impostor as LOD4** enabled, **Generate LOD Set** creates LOD0–LOD3 as geometry and automatically bakes LOD4 from the LOD0 source.

The old procedural `LOD4` proxy is still available manually.

## Automatic multi-view impostor baker

Select a generated tree and click **Bake Multi-View Impostor**.

Trees 2.0 will:

1. isolate the selected tree for rendering,
2. create a temporary orthographic camera and neutral light rig,
3. render evenly spaced azimuth views with a transparent background,
4. pack the RGBA views into a PNG atlas,
5. save atlas metadata on the tree,
6. create an optional view-selecting billboard mesh,
7. restore the original camera, render settings and object visibility.

The Blender preview impostor uses only **two triangles per baked view**. A game runtime can go even cheaper by using one camera-facing quad and selecting the atlas cell from camera azimuth.

See [`docs/advanced-growth-impostors.md`](docs/advanced-growth-impostors.md) for the advanced controls and engine metadata.

## Wind/export attributes

Branches can contain:

- `trees2_branch_level`
- `trees2_branch_id`
- `trees2_wind_weight`
- `trees2_wind_phase`
- `trees2_stiffness`

Foliage points contain:

- `trees2_rotation`
- `trees2_scale`
- `trees2_atlas_index`
- `trees2_wind_weight`
- `trees2_wind_phase`
- `trees2_stiffness`

Fused branches can reproject the branch/wind attributes after voxel remeshing.

## Export workflow

Keep foliage unrealized while authoring. Use **Bake Foliage for Export** only when you need actual card geometry for a mesh export.

For a complete game asset, generate close LODs normally and bake an impostor atlas for the final distance tier.

## Performance philosophy

Spend geometry where it produces visible silhouette and parallax:

- trunk and major branches — actual geometry,
- thin branches — progressively fewer radial sides,
- terminal detail — mostly foliage-card texture content,
- leaves — clustered 2D cards,
- very far distance — multi-view impostor.

## License

GPL-3.0-or-later.
