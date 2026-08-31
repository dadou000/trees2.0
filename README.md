# Trees 2.0

A Blender **5.2 LTS** extension for generating procedural, game-oriented trees without millions of leaf polygons.

The generator uses:

- Low-sided procedural branch meshes.
- Recursive seeded branching.
- Terminal-branch foliage distribution.
- One, two, or three crossed **2D leaf cards** per foliage point.
- Geometry Nodes **instances** for the foliage, so the source card mesh is shared instead of duplicated as separate Blender objects.
- Four LOD presets that reduce branch count, branch resolution, radial sides, and foliage density.
- Optional RGBA leaf-atlas textures.

## Current status

`0.1.0` is the first functional generator. It is intended as the base for species presets, more biologically accurate branching, wind attributes, atlasing tools, automatic impostors, and game-engine export helpers.

## Install in Blender 5.2 LTS

1. Download this repository as a ZIP, or build an extension ZIP with Blender's extension tooling.
2. In Blender open **Edit > Preferences > Extensions**.
3. Use **Install from Disk** and select the extension ZIP.
4. Enable **Trees 2.0** if required.
5. In the 3D View open the sidebar (`N`) and select the **Trees 2.0** tab.

The ZIP root must contain `blender_manifest.toml` and `__init__.py`.

## Basic workflow

1. Set the 3D cursor where the tree should be created.
2. Choose a seed and structural parameters.
3. Optionally select an RGBA leaf atlas in **Leaf Atlas**.
4. Keep **Realize Foliage** disabled while authoring for the lightest scene.
5. Click **Create Procedural Tree**.
6. Select the generated branch object, alter settings, then click **Regenerate Selected Tree**.
7. Use **Generate LOD Set** to produce LOD0-LOD3 side-by-side for visual comparison.

## Foliage architecture

Each generated tree has a hidden source leaf-card mesh. The visible foliage object contains points plus per-point rotation and scale attributes. A Geometry Nodes modifier instances the shared card mesh onto those points.

For a crossed card cluster:

- 1 foliage point = 2 quads = 4 render triangles.
- 2,000 foliage points = about 8,000 foliage triangles when realized.
- While unrealized, Blender keeps them as instances.

This is deliberately different from scanned foliage where every leaf can contain many triangles.

## Leaf atlas

The atlas should normally be an RGBA image with transparent background. The image color drives Base Color and its alpha drives Principled BSDF Alpha. Trees 2.0 uses Blender's dithered material transparency and renders both sides of the cards.

For best game results, use leaf-cluster textures that represent multiple leaves and small twigs on one card instead of one isolated leaf per card.

## LOD presets

| LOD | Intended use | Behavior |
|---|---|---|
| LOD0 | Hero / close | Full branches and foliage |
| LOD1 | Near | Fewer branches, segments and cards |
| LOD2 | Mid | Reduced recursive depth and foliage |
| LOD3 | Far | Very low branch and card count |

The exact polygon count depends on the generator settings and card style.

## Planned

- Species preset system.
- Crown shapes and apical-dominance models.
- Better branch junction geometry.
- Automatic bark UVs and texture variation.
- Leaf atlas cell randomization.
- Wind stiffness / branch hierarchy attributes.
- Automatic billboard/impostor LOD.
- Batch forest variation generator.
- GLTF/game-engine export helpers.
- Geometry Nodes-native live-edit mode.

## License

GPL-3.0-or-later.
