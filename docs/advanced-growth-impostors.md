# Trees 2.0 — Advanced Growth and LOD Pipeline

Version 0.3.0 adds three production-oriented systems on top of the existing procedural tree generator.

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

## Manifold parent/child branch junctions

**Fused Manifold** junction mode first builds the normal low-sided branch shells and then uses Blender 5.2's voxel remesher to turn the overlapping shells into one continuous manifold woody volume. Internal overlapping faces are removed, so child branches are no longer separate tubes intersecting the parent tube.

After remeshing, Trees 2.0 uses nearest-point reprojection to restore:

- `trees2_branch_level`
- `trees2_branch_id`
- `trees2_wind_weight`
- `trees2_wind_phase`
- `trees2_stiffness`

Bark image textures use box projection in fused mode because voxel remeshing rebuilds topology and destroys the original branch UV layout.

Use **Voxel Size** for the detail/cost tradeoff. Fused junctions are normally limited to close LODs; distant LODs keep cheap collars because their intersections are not visible.

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

- LOD0 — hero
- LOD1 — near
- LOD2 — mid
- LOD3 — far geometry
- LOD4 — automatically baked multi-view impostor

The old procedural LOD4 remains available manually by selecting `LOD4` in the normal optimization controls.
