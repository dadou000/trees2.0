# Trees 2.0 — Advanced Growth and LOD Pipeline

Version 0.3.1 keeps the competition-growth and impostor systems from 0.3.0 and replaces the experimental voxel-fusion junction system with Exact Boolean Junctions.

## Competition / space-colonization growth

When **Space Competition** is enabled, Trees 2.0 creates a virtual cloud of attraction points inside the selected crown profile. Growing branch segments are steered toward nearby unclaimed attraction points while an occupied-space field pushes them away from existing woody geometry.

As a segment enters new canopy space, nearby attraction points are removed. This makes later growth prefer the remaining empty volume instead of repeatedly sending branches through already occupied areas.

Controls:

- **Attraction Points** — resolution of the virtual canopy field.
- **Influence Radius** — how far a branch senses canopy targets.
- **Claim Radius** — how much target space a new segment consumes.
- **Branch Clearance** — preferred spacing from existing branch segments.
- **Attraction / Avoidance Strength** — balance crown filling and collision avoidance.
- **Competition Through LOD** — skip the more expensive pass on distant LODs.

The algorithm keeps the species preset's crown shape, apical dominance, droop, phototropism and branch distribution as priors. Competition modifies local growth direction rather than replacing species logic.

## Parent/child branch junctions

### Exact Boolean Junctions

This is now the production junction mode.

The generator first creates each woody branch as a closed solid. The trunk is used as the initial target and child branches are processed in hierarchy order. Major branch levels are progressively unioned into the growing trunk with Blender's **Exact Boolean** solver.

This avoids the failure mode of the previous whole-tree voxel remesh: the trunk is not globally resampled, so distant parts of the surface cannot become perforated merely because a local branch junction needs blending.

Controls:

- **Exact Through Branch Level** — highest branch hierarchy level that receives true Boolean union.
- **Exact Through LOD** — highest LOD that pays for exact junction construction.
- **Reproject Attributes** — restores branch hierarchy and wind metadata after topology changes.

The default is a hybrid tree:

- trunk, primary and secondary branch junctions: Exact Boolean,
- finer twigs: collar/intersection geometry.

That concentrates expensive topology work where players can actually see it.

### Failure handling

Each branch union is isolated. If one Boolean fails, that branch is retained and merged back as collar geometry. A failed union therefore cannot delete the branch or corrupt the rest of the trunk.

If the exact-junction setup fails before processing can complete, Trees 2.0 discards the partial result and rebuilds the known-safe collar version instead.

Generated metadata includes:

- `trees2_junction_mode`
- `trees2_exact_boolean_junctions`
- `trees2_collar_fallback_branches`
- `trees2_boolean_failures`
- `trees2_boolean_level_max`
- `trees2_boolean_lod_max`

After topology changes Trees 2.0 can restore:

- `trees2_branch_level`
- `trees2_branch_id`
- `trees2_wind_weight`
- `trees2_wind_phase`
- `trees2_stiffness`

Bark image textures use box projection in Exact Boolean mode to avoid UV discontinuities at newly-created junction faces.

## Automatic multi-view impostor LOD

Select a generated tree and choose **Bake Multi-View Impostor**. Trees 2.0 will:

1. Hide unrelated scene objects.
2. Create a temporary orthographic render camera and neutral lighting rig.
3. Render the tree from evenly spaced azimuth angles with transparent film.
4. Pack all RGBA views into one PNG atlas.
5. Save atlas metadata on the tree collection.
6. Create an optional multi-plane impostor object using the atlas.
7. Restore the original scene camera, render settings and visibility states.

The generated impostor has only **two triangles per baked view**. Its material uses backface culling and a facing threshold so only the plane closest to the viewing direction contributes.

For game-engine integration the object stores:

- `trees2_impostor_views`
- `trees2_impostor_columns`
- `trees2_impostor_rows`
- `trees2_impostor_atlas`
- `trees2_runtime_hint`

A runtime shader can replace the Blender preview mesh with one camera-facing quad and select the atlas frame from camera azimuth.

## Integrated LOD generation

With **Impostor as LOD4** enabled, **Generate LOD Set** creates:

- LOD0 — hero, including Exact Boolean major junctions by default
- LOD1 — near, including Exact Boolean major junctions by default
- LOD2 — mid
- LOD3 — far geometry
- LOD4 — automatically baked multi-view impostor

The old procedural LOD4 remains available manually by selecting `LOD4` in the normal optimization controls.
