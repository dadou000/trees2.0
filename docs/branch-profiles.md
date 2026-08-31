# Trees 2.0 — Realistic Branch Profiles

Version 0.3.3 replaces the visual cone-like radius progression of child branches with a post-growth biological profile pass.

The growth algorithm still decides branch position, direction, hierarchy, pruning and competition. The profile pass changes only branch radii, so space-colonization behavior and deterministic LOD derivation remain compatible.

## Radius model

A branch now has four broad longitudinal zones:

1. **Attachment / proximal swell** — the base receives a broad smooth swelling and part of the existing branch-collar value.
2. **Load-bearing section** — radius falls slowly and retains most of its base thickness.
3. **Distal taper** — stronger taper starts late in the branch instead of immediately after the attachment.
4. **Tip** — the final radius reaches a small configurable fraction of the branch base.

Low-frequency deterministic variation and one broad local knuckle are added along the branch. Variation fades toward the endpoints so the attachment and tip remain stable.

## Child / parent thickness

Branch base radius is derived from the radius of the parent limb at the actual attachment position.

Separate ratio ranges are used for:

- primary branches,
- secondary branches,
- tertiary and higher-order branches.

The base is capped below the parent radius so a child cannot become visually thicker than the limb that supports it.

## Built-in profiles

- **Automatic by Species** — resolves the profile from the current tree species preset.
- **Broadleaf** — balanced general-purpose broadleaf.
- **Heavy / Oak** — thick load-bearing limbs, late taper and stronger radius variation.
- **Slender / Birch** — lighter branch ratios and earlier taper.
- **Flexible / Willow** — slender branches with earlier, smoother taper.
- **Conifer** — lighter lateral branches with moderate thickness retention.
- **Custom** — exposes all radius-profile controls.

Automatic mapping groups related species. Oaks, chestnut, walnut, plane, apple, olive and baobab use the heavy profile; birch, alder, aspen, poplar, jacaranda and eucalyptus use the slender profile; conifer presets use the conifer profile.

## Custom controls

- **Hold Thickness** — fraction of base radius retained before the strong distal taper.
- **Taper Start** — normalized branch length where the strong taper begins.
- **Tip Thickness** — final radius as a fraction of branch base radius.
- **Taper Curve** — controls how strongly radius loss is delayed toward the tip.
- **Radius Variation** — amplitude of low-frequency irregularity and broad local swelling.
- **Base Swell** — proximal thickening around the attachment.
- **Primary / Secondary / Tertiary Min/Max** — child-to-parent base-radius ranges.
- **Taper Shift / Level** — makes higher-order twigs start tapering earlier.
- **Hold Loss / Level** — makes higher-order twigs retain less base thickness.
- **Branch-to-Branch Variation** — deterministic variation between limbs.

## LOD behavior

The profile pass runs on the LOD0 master skeleton. LOD1–LOD4 are derived from that profiled skeleton, so branch thickness does not reroll or change identity when the LOD changes. Lower LODs only simplify branch selection and polyline sampling.
