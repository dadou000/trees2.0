# Trees 2.0

A Blender **5.2 LTS** extension for generating game-ready procedural trees without millions of individually modeled leaves.

The design target is a traditional efficient vegetation pipeline brought into modern Blender:

- low-sided procedural branch meshes,
- shared 2D/bent foliage cards,
- Geometry Nodes instancing,
- texture-atlas variation,
- deterministic seeds,
- generated LODs,
- engine-oriented wind attributes,
- export-time foliage realization only when needed.

## Status

`0.2.0` is an authoring prototype intended for testing in Blender 5.2 LTS. Python syntax is checked in CI, but Blender-runtime behavior should still be treated as beta until exercised across several 5.2 builds and render/export paths.

## Installation

1. Download/clone the repository.
2. Package the extension so `blender_manifest.toml` and `__init__.py` are at the ZIP root.
3. In Blender 5.2: **Edit > Preferences > Get Extensions > Install from Disk**.
4. Enable **Trees 2.0** if needed.
5. Open the 3D View sidebar (`N`) and choose **Trees 2.0**.

## Generator model

### Structure

The generator builds a deterministic branch skeleton from a seed. Branches are converted directly to low-sided mesh tubes rather than high-resolution sculpted cylinders.

The current growth model includes:

- root flare,
- trunk taper and irregularity,
- 1–4 branch levels,
- golden-angle phyllotaxis, random, or whorled distribution,
- crown profiles (round, oval, columnar, conical, vase, umbrella),
- branch collars,
- branch bend and droop,
- upward-growth/phototropism bias,
- apical dominance,
- natural pruning,
- dead branch probability.

### Species starting presets

Included presets are deliberately parameter presets, not scanned species models:

- Generic Broadleaf
- Oak
- Birch
- Poplar
- Willow
- Pine

Apply a preset, then tune the individual growth controls.

## 2D foliage cards

Foliage is not modeled leaf-by-leaf.

Each foliage point instances one shared card cluster:

- **Single**: one bent card
- **Crossed**: two crossed bent cards
- **Tri-Cross**: three crossed bent cards

`Card Bend` introduces a small center fold so close cards do not read as perfectly flat planes.

### Texture atlas

Set:

- Atlas Columns
- Atlas Rows
- Used Cells

Trees 2.0 creates one shared source-card object per used atlas cell. Every foliage point receives a `trees2_atlas_index` integer and Geometry Nodes uses **Pick Instance** to choose the corresponding UV-mapped card source.

Optional maps:

- leaf color + alpha atlas,
- leaf normal atlas,
- leaf roughness atlas,
- bark color,
- bark normal.

The same atlas layout must be used by the leaf color/normal/roughness textures.

## Foliage distribution

Foliage is concentrated on terminal living branches, with controls for:

- density,
- start position along terminal branches,
- tip bias,
- cluster spread,
- up-orientation bias,
- card scale and random variation.

Dead branches intentionally receive no foliage.

## LODs

| LOD | Purpose | Behavior |
| --- | --- | --- |
| LOD0 | Hero | Full branch depth, highest radial resolution and foliage density |
| LOD1 | Near | Reduced branch count/segments/cards |
| LOD2 | Mid | Fewer branch levels and aggressive foliage reduction |
| LOD3 | Far | Minimal major branches and enlarged sparse cards |
| LOD4 | Proxy | Ultra-cheap tree-shaped proxy using very few branches/cards |

**Generate LOD Set** places LOD0–LOD4 side-by-side for inspection.

LOD4 is currently a geometric proxy. A future milestone is a true baked multi-angle impostor atlas generator.

## Wind/export attributes

When **Wind Attributes** is enabled the branch mesh contains:

- `trees2_branch_level` (integer)
- `trees2_branch_id` (integer)
- `trees2_wind_weight` (float)
- `trees2_wind_phase` (float)
- `trees2_stiffness` (float)

Foliage points contain:

- `trees2_rotation` (quaternion)
- `trees2_scale` (vector)
- `trees2_atlas_index` (integer)
- `trees2_wind_weight` (float)
- `trees2_wind_phase` (float)
- `trees2_stiffness` (float)

These are intended as stable metadata for later Blender shaders and game-engine export tooling.

## Export workflow

While authoring, keep **Realize Foliage** disabled. This keeps the Blender scene light because every foliage point is an instance.

When a selected tree is ready for mesh export, use **Bake Foliage for Export**. This applies the Geometry Nodes foliage modifier and removes the now-unused internal card-source collection.

The branch mesh has generated cylindrical UVs. Foliage cards use atlas-cell UVs.

## Existing-tree workflow

Each tree stores a JSON snapshot of its generation parameters on its root collection.

Select a generated tree and use:

- **Load Settings** to restore its parameters into the sidebar,
- **Regenerate Selected Tree** to rebuild it at the same location.

Texture image pointers are intentionally not serialized into the JSON snapshot.

## Performance philosophy

A tree should spend geometry where silhouette and parallax need it:

- trunk and major branches: actual geometry,
- progressively thinner branches: fewer radial sides,
- terminal detail: mostly foliage-card textures,
- leaves: grouped into card textures instead of modeled individually,
- far distance: progressively larger/fewer card clusters.

This is designed to avoid the multi-million-polygon vegetation workflow unless the asset genuinely requires that level of source detail.

## Planned next milestones

- true multi-angle impostor baking,
- branch-to-parent junction blending beyond intersecting collars,
- crown collision/space colonization so branches avoid occupying the same volume,
- obstacle/light-volume growth guides,
- roots and exposed buttress roots,
- seasonal leaf-loss controls,
- flower/fruit secondary card layers,
- wind preview Geometry Nodes/shader,
- Godot/Unreal-oriented export helpers,
- batch forest variation generation.

## License

GPL-3.0-or-later.
