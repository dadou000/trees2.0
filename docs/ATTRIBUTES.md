# Trees 2.0 generated attributes

These names are part of the intended exporter/shader interface. Avoid renaming them casually once external tooling begins to depend on them.

## Branch mesh point-domain attributes

| Attribute | Type | Meaning |
| --- | --- | --- |
| `trees2_branch_level` | Integer | 0 is trunk, 1+ are successive branch orders |
| `trees2_branch_id` | Integer | Stable ID within one generated tree |
| `trees2_wind_weight` | Float | Approximate flexibility contribution from height and branch order |
| `trees2_wind_phase` | Float | 0–1 per-branch phase seed for decorrelating wind motion |
| `trees2_stiffness` | Float | Approximate inverse flexibility weight |

## Foliage point-domain attributes

| Attribute | Type | Meaning |
| --- | --- | --- |
| `trees2_rotation` | Quaternion | Instance orientation |
| `trees2_scale` | Vector | Instance scale |
| `trees2_atlas_index` | Integer | Source-card/atlas-cell selection |
| `trees2_wind_weight` | Float | Height-driven foliage wind weight |
| `trees2_wind_phase` | Float | Per-cluster phase seed |
| `trees2_stiffness` | Float | Cluster stiffness hint |

Geometry Nodes instances are expected to carry point attributes onto the instance domain. Exporters may choose to realize instances and convert these attributes into vertex colors, custom vertex streams, object data, or engine-specific buffers.
