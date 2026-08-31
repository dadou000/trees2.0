# Procedural species PBR

Trees 2.0 v0.4.0 can synthesize exportable texture sets directly in Blender for every built-in species preset.

## Usage

Open **N > Trees 2.0 > Procedural PBR Textures**, choose a tree preset in the main panel, then click **Generate Species PBR**.

Generated images are assigned back to the active Trees 2.0 settings by default. Regenerate or create the tree afterward to build materials from the new maps.

If the `.blend` has been saved, the default output is `//trees2_generated_pbr/<species>/`. For an unsaved file, Trees 2.0 uses Blender's temporary directory.

## Leaf / needle atlas

Broadleaf presets generate a multi-cell RGBA atlas. Conifer presets generate needle or scale-spray cards. Each atlas also receives a matching tangent-space normal atlas and roughness atlas.

Outputs:

- `<species>_leaf_albedo.png` — species color + alpha mask
- `<species>_leaf_normal.png`
- `<species>_leaf_roughness.png`

The default 4x4 grid gives 16 deterministic variants. Atlas rows are generated in the same top-to-bottom indexing convention used by Trees 2.0 card UVs.

Leaf morphology families include oval, round, triangular, heart-shaped, lanceolate, lobed, maple-like, compound, needle, and scale/spray forms. Profiles also control serration, vein color, cluster count, roughness, damage, and normal strength.

## Bark

Bark is generated from periodic functions so the image tiles at its borders. Species profiles control vertical ridges, fissure frequency/depth, plate breakup, fine surface noise, color, roughness, AO strength, and normal amplitude.

Outputs:

- `<species>_bark_albedo.png`
- `<species>_bark_normal.png`
- `<species>_bark_roughness.png`
- `<species>_bark_height.png`
- `<species>_bark_ao.png`

Generated bark materials automatically multiply AO into albedo, use the roughness map, combine the normal map with a light height/bump pass, and remain compatible with the existing branch UV/box-projection paths.

## Preset coverage

All current presets have explicit PBR profiles: Generic Broadleaf; English, Holm and Cork Oak; Birch; Beech; Maple; Ash; Elm; Linden; Chestnut; Walnut; London Plane; Alder; Aspen; Poplar; Willow; Cherry; Apple; Magnolia; Jacaranda; Eucalyptus; Olive; Acacia; Baobab; Scots Pine; Stone Pine; Norway Spruce; Silver Fir; Cedar; Italian Cypress; Coast Redwood; Dead Tree; Windswept; and Young Sapling.

The Dead Tree profile intentionally skips foliage generation and produces only weathered bark.

## Performance

512px is the default for both leaf atlases and bark sets. 1024/2048px generation is substantially more expensive because the current synthesizer is CPU/Python based. The generated PNGs are intended to be reused across many trees of the same species rather than regenerated per instance.
